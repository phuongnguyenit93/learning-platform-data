# NumberStyleFormatter, CurrencyStyleFormatter, and PercentStyleFormatter in Spring Framework

> **Topic:** Spring Framework – validation, data binding, and type conversion.  
> **Group:** Number formatting.  
> **Example environment:** Java 17+, Spring Framework 6.2.x. This article explains how to parse strings into numbers and print numbers as strings by locale/pattern, how to integrate formatters into Spring MVC, and the boundaries to manage for currency/percentages.

## 1. Why do we need number formatters?

Numeric values are structured data; their display string depends on the locale. The same value `12345.67` can be presented as follows:

| Locale | Sample Representation |
| --- | --- |
| `en-US` | `12,345.67` |
| `de-DE` | `12.345,67` |
| `fr-FR` | `12 345,67` |

Currency also includes symbols and fractional digits; percentages use a convention of multiplying the ratio value by 100 when displaying. Therefore, you should not manually replace commas/dots or parse numbers using the server's default locale.

Spring provides three specialized formatters:

- `NumberStyleFormatter`: standard numbers by locale or decimal pattern.
- `CurrencyStyleFormatter`: currency-style numbers, allowing configuration of currency, fraction digits, and rounding.
- `PercentStyleFormatter`: locale-specific percentage-style numbers.

All three perform bidirectional parsing and printing. This is useful for forms: input data is converted into Java numeric types; when rendered again, the value can be formatted according to the current locale.

## 2. Formatter contract: parse and print

In Spring, `Formatter<T>` combines `Parser<T>` and `Printer<T>`. The two core operations are:

```java
public interface Formatter<T> extends Printer<T>, Parser<T> {
    // parse(String text, Locale locale)
    // print(T object, Locale locale)
}
```

- `parse(text, locale)` converts text into a Java value.
- `print(object, locale)` produces display text.
- `Locale` determines the decimal separator, digit grouping, and currency/percent symbols.
- Parse failures may throw `ParseException`; when flowing through Spring binding, errors are translated into appropriate binding errors.

Unlike a unidirectional `Converter<S,T>`, a formatter provides both a parser and a printer. When the same field needs to accept formatted input and render it back according to the corresponding convention, a formatter is the right abstraction.

## 3. NumberStyleFormatter: standard numbers

`org.springframework.format.number.NumberStyleFormatter` is a general-purpose formatter for `Number`. It uses a locale-based number format corresponding to `NumberFormat.getInstance(locale)`. The formatter allows configuring a decimal pattern using Java `DecimalFormat` syntax.

The Spring 6.2.14 Javadoc describes that this formatter's parsing returns `BigDecimal`, avoiding precision loss when parsing decimal strings.

### 3.1. Parsing and printing by locale

```java
import java.math.BigDecimal;
import java.util.Locale;
import org.springframework.format.number.NumberStyleFormatter;

NumberStyleFormatter formatter = new NumberStyleFormatter();

BigDecimal us = (BigDecimal) formatter.parse("12,345.67", Locale.US);
BigDecimal de = (BigDecimal) formatter.parse("12.345,67", Locale.GERMANY);

String displayUs = formatter.print(us, Locale.US);
String displayDe = formatter.print(de, Locale.GERMANY);
```

With the right locale, grouping and decimal separators are interpreted according to that locale's conventions. For instance, `1,234` can be interpreted differently between two locales; therefore, choose the locale based on the input contract/user context rather than guessing.

For machine-to-machine APIs, consider using numeric JSON representations or a fixed standard format. User-facing localized strings should not become an undefined integration format.

### 3.2. Decimal patterns

You can pass a pattern to the constructor or use `setPattern`:

```java
NumberStyleFormatter twoDecimals =
        new NumberStyleFormatter("#,##0.00");

NumberStyleFormatter threeOptional =
        new NumberStyleFormatter("#,##0.###");
```

| Pattern | Meaning |
| --- | --- |
| `#,##0` | Grouping and at least one integer digit |
| `#,##0.00` | Displays two decimal digits |
| `#,##0.###` | Up to three decimal digits |
| `0.000` | Displays three decimal digits |
| `#,##0.00;(#,##0.00)` | Positive pattern; negative pattern uses parentheses |

Patterns affect parsing/printing and visual presentation. They do not impose scale, precision, or valid domain range rules. For example, restricting a quantity to at most two decimal digits should be enforced in validation/domain logic, not just by having the formatter display two digits.

### 3.3. When to use it?

Use `NumberStyleFormatter` for quantities, scores, measurements, decimal ratios, or standard `BigDecimal` values. If a value represents currency or percentages, a specialized formatter usually expresses the intent better.

## 4. CurrencyStyleFormatter: monetary amounts

`org.springframework.format.number.CurrencyStyleFormatter` uses the currency style of `NumberFormat.getCurrencyInstance(locale)`. The formatter parses to `BigDecimal` and allows configuring the currency unit, fraction digits, rounding mode, and pattern.

Key APIs:

| API | Purpose |
| --- | --- |
| `setCurrency(Currency)` | Sets a specific currency when the business unit is known |
| `setFractionDigits(int)` | Sets the number of decimal digits; default is 2 |
| `setRoundingMode(RoundingMode)` | Sets the rounding mode; default is `UNNECESSARY` |
| `setPattern(String)` | Sets a decimal pattern |
| `setLenient(boolean)` | Controls how permissive parsing is |

### 4.1. Currency and Locale are two different concepts

Locale provides presentation conventions, such as grouping separators and symbol placement. Currency identifies the actual monetary unit such as USD, EUR, or VND. A user's locale does not prove the transaction's currency unit.

If the currency is known, configure it explicitly:

```java
import java.math.BigDecimal;
import java.util.Currency;
import java.util.Locale;
import org.springframework.format.number.CurrencyStyleFormatter;

CurrencyStyleFormatter usd = new CurrencyStyleFormatter();
usd.setCurrency(Currency.getInstance("USD"));
usd.setFractionDigits(2);

BigDecimal amount = usd.parse("$1,234.50", Locale.US);
String display = usd.print(amount, Locale.US);
```

Symbols and symbol placement follow the locale. If the system supports multiple currencies, store the currency alongside the amount or use a money value object. Do not infer currency solely from the `$` sign since multiple currencies share that symbol.

### 4.2. Rounding mode

The default `RoundingMode.UNNECESSARY` means the formatter must not silently round if parsing requires rounding under the configured fraction digits. When policy permits rounding, set the mode explicitly:

```java
import java.math.RoundingMode;

usd.setFractionDigits(2);
usd.setRoundingMode(RoundingMode.HALF_UP);
```

Common modes:

| Mode | Meaning |
| --- | --- |
| `HALF_UP` | Nearest neighbor; ties round up away from zero |
| `HALF_EVEN` | Nearest neighbor; ties round to the even digit |
| `DOWN` | Truncate remainder toward zero |
| `CEILING` | Round toward positive infinity |
| `FLOOR` | Round toward negative infinity |
| `UNNECESSARY` | Reject if rounding is required |

Rounding is a business/accounting policy. Do not pick a mode just to make an example run; define the rule at the appropriate calculation and storage step. A currency formatter does not check account balances, taxes, transaction permissions, or credit limits.

### 4.3. Notes on BigDecimal

Use `BigDecimal` for monetary amounts requiring decimal precision, never `double`. Distinguish between data scale, display fraction digits, and rounding mode. For example, `new BigDecimal("1.2300")` and `new BigDecimal("1.23")` compare equal via `compareTo` but differ under `equals` due to scale.

Do not use `new BigDecimal(0.1)` because the input is a binary floating-point approximation. Use `new BigDecimal("0.1")` or design for storing minor units where appropriate for the domain.

## 5. PercentStyleFormatter: percentage values

`org.springframework.format.number.PercentStyleFormatter` uses the percent style of `NumberFormat.getPercentInstance(locale)`. Parsing returns `BigDecimal`.

If the domain stores a ratio `0.125`, the percent style typically displays `12.5%`. Parsing `12.5%` returns the ratio `0.125`:

```java
import java.math.BigDecimal;
import java.util.Locale;
import org.springframework.format.number.PercentStyleFormatter;

PercentStyleFormatter percent = new PercentStyleFormatter();

String display = percent.print(new BigDecimal("0.125"), Locale.US);
BigDecimal ratio = (BigDecimal) percent.parse("12.5%", Locale.US);
```

Do not pass `12.5` when the domain stores a ratio and expect the formatter to treat it as 12.5%; the percent style applies `NumberFormat`'s percentage convention.

Two different ways to store data:

- **Ratio:** `0.125` represents 12.5%; convenient for multiplication calculations.
- **Percentage points:** `12.5` represents 12.5 percentage points.

Do not mix the two models in the same field. The percent formatter only parses/prints; it does not check for negative discounts, out-of-bounds tax rates, or completion rates above 100%.

## 6. Comparing the three formatters

| Criterion | NumberStyleFormatter | CurrencyStyleFormatter | PercentStyleFormatter |
| --- | --- | --- | --- |
| Target | General numbers | Currency-formatted numbers | Percentage-formatted numbers |
| Underlying NumberFormat | `getNumberInstance(locale)` | `getCurrencyInstance(locale)` | `getPercentInstance(locale)` |
| Parse result | `BigDecimal` | `BigDecimal` | `BigDecimal` |
| Locale | Grouping and decimal | Grouping, decimal, and currency style | Grouping, decimal, and percent symbol |
| Customization | `setPattern` | Currency, fraction digits, rounding, pattern | Locale percent style |
| Suitable data | Quantities, measurements | Amount with currency | Ratios/percentages |
| Business validation | Still required | Still required | Still required |

All three support parsing and printing. Choose based on the data's meaning, not just the string's appearance.

## 7. Runnable Java 17 example with Maven

The example below tests all three formatters with `Locale.US`. It uses Spring Framework 6.2.14 and needs no Spring Boot, servlet container, or database.

Structure:

```text
number-format-demo/
  pom.xml
  src/main/java/demo/NumberFormatterDemo.java
```

### 7.1. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>number-format-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.14</version>
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

### 7.2. NumberFormatterDemo.java

```java
package demo;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Currency;
import java.util.Locale;

import org.springframework.format.number.CurrencyStyleFormatter;
import org.springframework.format.number.NumberStyleFormatter;
import org.springframework.format.number.PercentStyleFormatter;

public final class NumberFormatterDemo {

    public static void main(String[] args) throws Exception {
        Locale locale = Locale.US;

        NumberStyleFormatter number = new NumberStyleFormatter();
        BigDecimal parsedNumber =
                (BigDecimal) number.parse("1,234.50", locale);
        String printedNumber = number.print(parsedNumber, locale);

        CurrencyStyleFormatter currency =
                new CurrencyStyleFormatter();
        currency.setCurrency(Currency.getInstance("USD"));
        currency.setFractionDigits(2);
        currency.setRoundingMode(RoundingMode.HALF_UP);

        BigDecimal parsedAmount =
                currency.parse("$1,234.50", locale);
        String printedAmount =
                currency.print(parsedAmount, locale);

        PercentStyleFormatter percent =
                new PercentStyleFormatter();
        BigDecimal parsedRatio =
                (BigDecimal) percent.parse("12.5%", locale);
        String printedPercent =
                percent.print(parsedRatio, locale);

        System.out.println("numberValue=" + parsedNumber.toPlainString());
        System.out.println("numberDisplay=" + printedNumber);
        System.out.println("currencyValue=" + parsedAmount.toPlainString());
        System.out.println("currencyDisplay=" + printedAmount);
        System.out.println("percentRatio=" + parsedRatio.toPlainString());
        System.out.println("percentDisplay=" + printedPercent);
    }
}
```

Run with JDK 17+ and Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.NumberFormatterDemo
```

Expected stdout with the US locale and standard JDK locale data:

```text
numberValue=1234.50
numberDisplay=1,234.50
currencyValue=1234.50
currencyDisplay=$1,234.50
percentRatio=0.125
percentDisplay=12.5%
```

The example fixes `Locale.US` so results are easy to verify. Currency symbols and spacing may depend on locale data/JDK; when writing production tests, pin the locale and verify output on the target JDK. This example is a complete program with Maven dependencies; running `javac` alone without Spring on the classpath will not compile.

## 8. Registering formatters in Spring MVC

Spring MVC lets you register formatters via `WebMvcConfigurer` and `FormatterRegistry`:

```java
package demo.web;

import java.math.BigDecimal;
import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.format.number.NumberStyleFormatter;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class NumberFormattingConfig implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addFormatterForFieldType(
                BigDecimal.class,
                new NumberStyleFormatter("#,##0.00"));
    }
}
```

This is a general formatter configuration for `BigDecimal` properties in the MVC registry. When a field needs specific currency or percentage rules, do not apply a generic formatter and expect it to know each field's semantics. Using annotations or field-specific configuration is more appropriate.

### 8.1. Using @NumberFormat per field

Spring provides the `@NumberFormat` annotation to choose a style per field:

```java
import java.math.BigDecimal;
import org.springframework.format.annotation.NumberFormat;
import static org.springframework.format.annotation.NumberFormat.Style.CURRENCY;
import static org.springframework.format.annotation.NumberFormat.Style.NUMBER;
import static org.springframework.format.annotation.NumberFormat.Style.PERCENT;

public class InvoiceForm {

    @NumberFormat(style = NUMBER)
    private BigDecimal quantity;

    @NumberFormat(style = CURRENCY)
    private BigDecimal total;

    @NumberFormat(style = PERCENT)
    private BigDecimal discountRate;

    // getters and setters
}
```

Spring uses an annotation formatter factory to select the corresponding formatter:
- `quantity` uses number style.
- `total` uses currency style.
- `discountRate` uses percent style.

`@NumberFormat(style=CURRENCY)` selects locale-based currency formatting; this annotation does not itself represent a fixed transaction currency such as USD. If the currency unit is known, configure it explicitly or use a value object carrying the currency.

### 8.2. Form binding and validation

Spring MVC form binding can parse strings into `BigDecimal` via registered formatters/annotations. After binding, `@Valid` can trigger Bean Validation:

```java
@PostMapping("/invoice")
public String submit(
        @Valid @ModelAttribute("invoiceForm") InvoiceForm form,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return "invoice-form";
    }
    return "invoice-preview";
}
```

This is an illustrative method inside an MVC controller with corresponding views. `BindingResult` must be placed immediately after the model attribute to receive form binding/validation errors.

For `@RequestBody` JSON, payloads typically go through an `HttpMessageConverter` such as Jackson and its own deserialization pipeline. Do not assume MVC's formatter registry controls all JSON numbers/strings. Define the JSON representation and configure Jackson/custom deserializers as needed.

## 9. Locale and handling user input

Locale determines the decimal separator and grouping. The same `BigDecimal("1234.50")` can print as different strings:

```java
NumberStyleFormatter formatter = new NumberStyleFormatter();
BigDecimal amount = new BigDecimal("1234.50");

String us = formatter.print(amount, Locale.US);
String germany = formatter.print(amount, Locale.GERMANY);
```

When parsing back, you must use a locale matching how the string was entered. Do not parse `"1.234,50"` with `Locale.US` and expect the same value.

In Spring MVC, the active locale can be determined by a locale resolver/interceptor and request context. Tests should verify the actual request locale. For HTML `<input type="number">`, browsers have their own HTML-defined formatting/submission rules; do not assume every field submits localized text matching display content.

For machine-to-machine APIs, prefer stable representations independent of UI language. Locale-aware formatters are generally suited for forms and display content.

## 10. Parse errors, leniency, and validation

A formatter does not make invalid data valid. Scenarios:
- String not formatted as a number for the locale: parse error.
- Currency string incompatible with symbol/locale: parse error or dependent on the number format.
- Percentage value may parse successfully yet violate policy.
- Currency with restricted fraction digits where input requires rounding: with default `UNNECESSARY`, parsing may reject it.

`AbstractNumberFormatter` provides `setLenient(boolean)` to adjust parsing flexibility. Lenient parsing may accept broader inputs depending on the number format; strict input is usually easier to control. Do not enable lenient mode just to reduce errors if ambiguous strings could be interpreted unexpectedly.

Separate responsibilities:

1. **Parse/format:** can the string be converted to a numeric value under the locale/pattern?
2. **Bean Validation:** does the value satisfy required, min/max, or scale constraints?
3. **Business rules:** is the amount/rate allowed in the use case?
4. **Persistence:** do the database's precision/scale preserve the value?

Validation example:

```java
import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotNull;
import java.math.BigDecimal;

public class DiscountForm {

    @NotNull
    @DecimalMin("0.0")
    @DecimalMax("1.0")
    private BigDecimal rate;

    // getter and setter
}
```

Here the domain stores a ratio from 0 to 1. If the field stores percentage points from 0 to 100, the bounds must be different. The formatter does not decide that data model.

## 11. Precision, scale, and display

Distinguish between:
- **Precision:** total number of significant digits.
- **Scale:** number of digits to the right of the decimal point in a `BigDecimal` representation.
- **Display fraction digits:** number of digits printed by the formatter.
- **Rounding mode:** how to handle values that cannot be represented at the requested scale.

For example, `BigDecimal("1.2300")` has scale 4; a formatter with a two-digit pattern may display `1.23`. Displaying two digits does not prove the underlying data has been normalized to scale 2.

If scale is a domain invariant, normalize/validate explicitly. For currency, apply rounding at the appropriate business calculation step; do not let the formatter alter data merely because the UI wants fewer digits.

## 12. Common pitfalls

**1. Using NumberStyleFormatter for money without storing the currency.** A number alone does not indicate USD, EUR, or VND.

**2. Confusing ratios and percentage points.** `0.125` and `12.5` differ by a factor of 100 when using percent style.

**3. Parsing a localized string with the wrong locale.** Commas and periods can have opposite meanings.

**4. Using double for amounts.** Binary floating-point numbers can introduce inaccuracies; use `BigDecimal`.

**5. Assuming the formatter performs validation.** Successful parsing does not prove an amount/rate is valid.

**6. Failing to decide a rounding mode.** `CurrencyStyleFormatter` defaults to `UNNECESSARY`; cases needing rounding may be rejected.

**7. Thinking @NumberFormat sets a fixed currency.** The annotation selects the style; transaction currency may need separate configuration.

**8. Expecting FormatterRegistry to handle all JSON bodies.** JSON typically goes through Jackson/`HttpMessageConverter`; test and configure separately.

**9. Not pinning the locale in tests.** Expected strings vary by locale/JDK data.

**10. Using patterns in place of domain constraints.** Display patterns do not enforce ranges, precision, or business permissions.

## 13. Recommended test matrix

| Case | What to Verify |
| --- | --- |
| Number parse `1,234.50` with `Locale.US` | `BigDecimal` 1234.50 |
| Number parse `1.234,50` with `Locale.GERMANY` | `BigDecimal` 1234.50 |
| Print the same number for US and Germany | Decimal/group separators differ |
| Currency parse `$1,234.50` with US/USD | `BigDecimal` 1234.50 |
| Currency fraction digits 2 and exact scale value | Parse/print succeeds |
| Currency input requiring rounding | Follows selected rounding mode; default may reject |
| Percent parse `12.5%` with US | Ratio 0.125 |
| Percent print 0.125 with US | `12.5%` |
| Number string with wrong locale | Parse/binding error |
| `@NumberFormat` on individual fields | Each field applies the right style |
| Localized MVC form | Uses the request's locale |
| `@RequestBody` JSON | Test Jackson representation separately |

Tests should be split into three levels: direct formatter unit tests; binding tests with `DataBinder`/MVC; and domain/service tests for ranges, currency, and rounding. When asserting locale output, pass an explicit locale and pin the test environment.

## 14. Choosing the right formatter

- Use **NumberStyleFormatter** for general numbers needing locale- or pattern-based parsing/printing.
- Use **CurrencyStyleFormatter** for monetary amounts; set currency and rounding mode according to policy.
- Use **PercentStyleFormatter** for rates stored as ratios and displayed in percent style.
- Use **@NumberFormat** when each form field needs an individually declared style.
- Use **FormatterRegistry/WebMvcConfigurer** when integrating formatters into MVC binding.
- Use custom converters/deserializers when input formats follow a contract different from default formatters.

**Remember:** `NumberStyleFormatter` formats numbers; `CurrencyStyleFormatter` formats currency amounts; `PercentStyleFormatter` formats ratios. All three parse/print by locale and support `BigDecimal`. Determine locale, currency, scale, and rounding up front; continue enforcing validation/domain rules after parsing.

## Official references

- [Spring Framework 6.2 – Field Formatting](https://docs.spring.io/spring-framework/reference/6.2/core/validation/format.html): Formatter, locale, and annotation formatting.
- [NumberStyleFormatter Javadoc 6.2.14](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/format/number/NumberStyleFormatter.html): number style, BigDecimal parsing, and patterns.
- [CurrencyStyleFormatter Javadoc 6.2.14](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/format/number/CurrencyStyleFormatter.html): currency, fraction digits, and rounding modes.
- [PercentStyleFormatter Javadoc 6.2.14](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/format/number/PercentStyleFormatter.html): percent style and BigDecimal parsing.
- [Spring MVC Type Conversion](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/conversion.html): registering Formatters and Converters via WebMvcConfigurer.
