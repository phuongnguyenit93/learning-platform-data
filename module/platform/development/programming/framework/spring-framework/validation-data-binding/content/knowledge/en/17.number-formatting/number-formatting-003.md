# Custom Number Patterns and Locale Separators in Spring

## 1. Why are custom number patterns and Locale needed?

A Java numeric value can be displayed and entered under multiple regional conventions. For example, the same value `1234.50` can be represented as:

| Locale | Common Representation | Separator Meaning |
| --- | --- | --- |
| en-US | 1,234.50 | Comma for thousands grouping, period for decimal |
| de-DE | 1.234,50 | Period for grouping, comma for decimal |
| fr-FR | 1 234,50 | Grouping separator is often a narrow space, comma for decimal |

This is still the exact same numeric value, yet the character string varies by Locale and formatting rules. If an application receives `1.234,50` and parses it using `en-US` rules, the result may be wrong or rejected. If code arbitrarily strips dots/commas, the data can silently turn into a different number.

In Spring, the primary components involved include:

- **@NumberFormat**: declares a formatting pattern or style on a field/property.
- **NumberStyleFormatter**: number formatter using pattern and Locale.
- **CurrencyStyleFormatter**, **PercentStyleFormatter**: currency/percent formatters.
- **FormattingConversionService**: integrates Formatters into the `ConversionService` mechanism.
- **LocaleContextHolder** in web requests: provides the request-scoped Locale when Spring MVC performs formatting.

Distinguish three concerns: how numbers are displayed; how user strings are parsed; and business rules such as positive amounts, maximum decimal digits, or value bounds. Formatting does not replace validation.

## 2. DecimalFormat number pattern syntax

Spring's number formatters build on Java's formatting APIs, especially **java.text.NumberFormat** and **java.text.DecimalFormat**. Common patterns use the following symbols:

| Symbol | Meaning | Example |
| --- | --- | --- |
| 0 | Required digit; displays 0 if missing | 000 |
| # | Optional digit; omits leading/trailing zeros | ### |
| , | Integer grouping separator in non-localized patterns | #,##0 |
| . | Decimal separator in non-localized patterns | 0.00 |
| % | Multiplies value by 100 when formatting | 0.00% |
| ‰ | Multiplies by 1000 when formatting | 0.0‰ |
| E | Scientific exponent notation | 0.00E0 |
| ; | Separates positive and negative patterns | #,##0.00;(#,##0.00) |
| ' | Quotes special characters as literals | #,##0.00 'USD' |

Examples with `en-US`:

| Pattern | Value | Display |
| --- | ---: | --- |
| 0 | 7.2 | 7 |
| 0.00 | 7.2 | 7.20 |
| #,##0.## | 1234.5 | 1,234.5 |
| #,##0.00 | 1234.5 | 1,234.50 |
| 00000 | 42 | 00042 |
| #,##0.00;(#,##0.00) | -1234.5 | (1,234.50) |
| 0.0% | 0.125 | 12.5% |

### 2.1. Distinguishing 0 and #

`0` preserves a digit at a minimum position; `#` only displays a digit if corresponding data exists. The pattern `000.00` guarantees at least three integer digits and two decimal digits. The pattern `#,##0.00` is typically suited for reports requiring two decimal places.

An account number like `001234` is an identifier string, not a numeric quantity. If stored as a `Number`, leading zeros may be lost and the data's meaning changes.

### 2.2. Grouping separator and decimal separator

In non-localized patterns, comma and period have fixed syntactic roles: comma means grouping, period means decimal. When `DecimalFormat` is created with a `Locale`, the pattern is applied using that Locale's `DecimalFormatSymbols`.

~~~java
new DecimalFormat("#,##0.00",
        DecimalFormatSymbols.getInstance(Locale.US));

new DecimalFormat("#,##0.00",
        DecimalFormatSymbols.getInstance(Locale.GERMANY));
~~~

With the same pattern but different symbols, `1234.5` displays as `1,234.50` and `1.234,50` respectively. Do not confuse a non-localized pattern with a localized pattern. There is no need to flip pattern characters just because the German Locale uses reversed display separators.

### 2.3. Percent and per mille are multiplications

The pattern `0.00%` multiplies the value by 100 when formatting and divides by the corresponding factor when parsing. Thus `0.125` displays as `12.50%`. If the database already stores `12.5` instead of `0.125`, applying a percent format can display `1250%`. Establish the storage convention before choosing a formatter.

## 3. Locale determines symbols and string parsing

Locale affects:
- Decimal separator: character separating integer and fractional parts.
- Grouping separator: character separating digit groups.
- Digit symbols and representation conventions.
- Currency symbol when using a currency formatter.
- Certain default styles.

~~~java
NumberFormat us = NumberFormat.getNumberInstance(Locale.US);
NumberFormat germany = NumberFormat.getNumberInstance(Locale.GERMANY);
NumberFormat france = NumberFormat.getNumberInstance(Locale.FRANCE);
~~~

For the same `BigDecimal` `1234.50`, formatting with each Locale yields different representations. French grouping separators may be narrow non-breaking spaces depending on JDK/CLDR; do not hardcode display characters based on a single runtime environment.

### 3.1. Source Locale and target Locale

When formatting for display, use the viewer's or report's Locale. When parsing incoming data, use the Locale specified by the input contract. These two Locales can differ.

For example, a web page displays in `vi-VN`, while an integration API requires a fixed format using a decimal period and no grouping. You should not parse API input using an arbitrary browser Locale when the API publishes its own format.

The string `1,234` can be interpreted as one thousand two hundred thirty-four or one point two three four depending on convention. If the client changes Locale, there is no safe way to guess without an explicit contract.

### 3.2. Locale does not determine the unit

The German Locale may supply the Euro symbol in currency style, yet that does not mean every `BigDecimal` is EUR. Monetary amounts need an explicit currency code/unit in the model or API contract. Never use Locale to infer business units.

## 4. Spring @NumberFormat and number formatters

### 4.1. Declaring on fields/properties

~~~java
public class InvoiceForm {

    @NumberFormat(pattern = "#,##0.00")
    private BigDecimal netAmount;

    @NumberFormat(style = NumberFormat.Style.CURRENCY)
    private BigDecimal grossAmount;

    @NumberFormat(style = NumberFormat.Style.PERCENT)
    private BigDecimal discountRate;

    // Getters and setters...
}
~~~

- **pattern** is for application-defined number patterns.
- **style** offers `NUMBER`, `CURRENCY`, or `PERCENT`.
- Even with an explicit `pattern`, the formatter still uses `Locale` to determine `DecimalFormatSymbols` during parse/print.
- The annotation does not enforce min/max rules, business scale, or an entity's currency code.

### 4.2. NumberStyleFormatter

`NumberStyleFormatter` uses a Locale-based `NumberFormat` and can accept a pattern:

~~~java
NumberStyleFormatter formatter =
        new NumberStyleFormatter("#,##0.00");

String text = formatter.print(
        new BigDecimal("1234.5"), Locale.GERMANY);
~~~

The expected value is `1.234,50`. It can be parsed with the corresponding Locale:

~~~java
Number value = formatter.parse("1.234,50", Locale.GERMANY);
~~~

This is a direct `Formatter` call. In Spring MVC, the Locale is typically obtained from the request's `LocaleContext`. Test parsing against the exact Spring version and Locale configured by your application.

### 4.3. CurrencyStyleFormatter and PercentStyleFormatter

- **CurrencyStyleFormatter** formats numbers according to the Locale's currency conventions. Consider currency code, fraction digits, and API contract.
- **PercentStyleFormatter** formats according to percentage conventions, applying the corresponding percentage factor.
- **NumberStyleFormatter** suits standard numbers and custom patterns.

Do not use a currency formatter as a substitute for a `Money` type or monetary model. Monetary values in business logic usually require both the amount and the currency code (EUR, USD, VND).

## 5. Custom separator symbols beyond built-in Locales

If a system has its own conventions, Java lets you construct **DecimalFormatSymbols**:

~~~java
DecimalFormatSymbols symbols =
        DecimalFormatSymbols.getInstance(Locale.US);

symbols.setDecimalSeparator(',');
symbols.setGroupingSeparator('.');
~~~

Then:

~~~java
DecimalFormat format =
        new DecimalFormat("#,##0.00", symbols);
~~~

Example result: `1234.5` displays as `1.234,50`. This is a custom symbols configuration; do not do this arbitrarily because the resulting string may be incompatible with default Locales, exported files, or other APIs.

Symbols must be distinguishable. If the decimal separator and grouping separator are identical, the parser cannot tell how to split them. Positive/negative prefixes and suffixes must also be distinct to parse negative signs accurately. Configure one symbol set per formatting contract and test both parsing and printing.

### 5.1. Grouping size

Grouping size is 3 digits in many Locales, though not every system groups by threes. `DecimalFormat` lets you change the grouping size:

~~~java
DecimalFormat format = new DecimalFormat("#,##0.00");
format.setGroupingSize(3);
~~~

Grouping size is the number of digits between grouping separators. If business rules require a different digit-grouping scheme, verify the Locale/implementation or build an appropriate formatter; do not assume every comma groups digits identically.

### 5.2. Prefix, suffix, and literals

You can add literals to a pattern, such as `#,##0.00 'kg'` or `¤ #,##0.00` for a currency symbol. Special characters must be quoted with single quotes to be treated as plain text.

Positive/negative patterns can be written as:

~~~text
#,##0.00;(#,##0.00)
~~~

This displays negative numbers in parentheses. The negative subpattern mainly defines the prefix/suffix; digit count rules are generally shared with the positive pattern.

Physical units, currency codes, or percentages must match the stored value. A pattern only controls presentation and does not prove the unit or value is valid.

## 6. Rounding, scale, and precision

`DecimalFormat` defaults to **RoundingMode.HALF_EVEN**. Values with more fractional digits than the display pattern may be rounded.

The application must decide:
- Does the calculated result stored in the database retain its original scale?
- Should we only format for display or persist the rounded value?
- Is the rule `HALF_UP`, `HALF_EVEN`, `DOWN`, or something else?
- Does the number of decimal digits for money depend on the currency?
- If the user enters more digits than allowed, should we reject or round?

Display formatting should not silently turn into business computation. For money, use **BigDecimal** and apply scale/rounding explicitly in the domain/service layer.

~~~java
BigDecimal amount = new BigDecimal("12.345");
BigDecimal rounded =
        amount.setScale(2, RoundingMode.HALF_UP);
~~~

The result is `12.35`. This is actual rounding in domain code; it is not the same as `DecimalFormat` merely printing two digits on screen.

## 7. Strict parsing: validating the entire string

An easily overlooked detail is that `NumberFormat.parse(String)` can parse only a prefix of a string. For example, `"123abc"` should not be considered a valid number just because the parser read the `123` prefix.

For input that must match completely, use **ParsePosition** and verify:
- The parsed result is non-null.
- `errorIndex` reports no error.
- The final index equals the string's length.
- There is an explicit rule for leading/trailing whitespace.
- The value does not exceed business limits or scale.

Not every default Spring formatter shares the same strictness policy. If an endpoint requires the entire string to match, add a verification step or write a custom `Formatter`/`Converter` with a clear contract.

## 8. Runnable Java 17+ example: custom pattern and Locale

The following program uses only the JDK. It demonstrates:
1. Formatting the same `BigDecimal` using US and German symbols.
2. Parsing strings accurately under the corresponding Locale.
3. Strict parsing to reject input with trailing characters.
4. Custom pattern and explicit rounding mode.

Structure:

~~~text
number-locale-demo/
└── NumberLocaleDemo.java
~~~

**NumberLocaleDemo.java**:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.ParsePosition;
import java.util.Locale;

public final class NumberLocaleDemo {

    private static DecimalFormat createFormat(Locale locale) {
        DecimalFormatSymbols symbols =
                DecimalFormatSymbols.getInstance(locale);

        DecimalFormat format =
                new DecimalFormat("#,##0.00;(#,##0.00)", symbols);

        format.setParseBigDecimal(true);
        format.setRoundingMode(RoundingMode.HALF_EVEN);
        return format;
    }

    private static BigDecimal parseStrict(
            DecimalFormat format, String text) {

        ParsePosition position = new ParsePosition(0);
        Number parsed = format.parse(text, position);

        if (parsed == null
                || position.getErrorIndex() >= 0
                || position.getIndex() != text.length()) {
            throw new IllegalArgumentException(
                    "Invalid number for selected locale");
        }

        if (parsed instanceof BigDecimal decimal) {
            return decimal;
        }
        return new BigDecimal(parsed.toString());
    }

    public static void main(String[] args) {
        BigDecimal value = new BigDecimal("1234.5");

        DecimalFormat us = createFormat(Locale.US);
        DecimalFormat germany = createFormat(Locale.GERMANY);

        String usText = us.format(value);
        String germanText = germany.format(value);

        System.out.println("US_FORMAT=" + usText);
        System.out.println("DE_FORMAT=" + germanText);

        System.out.println("US_PARSE="
                + parseStrict(us, usText).toPlainString());
        System.out.println("DE_PARSE="
                + parseStrict(germany, germanText).toPlainString());

        try {
            parseStrict(us, "1,234.50xyz");
            System.out.println("STRICT_PARSE=unexpected-success");
        } catch (IllegalArgumentException ex) {
            System.out.println("STRICT_PARSE=rejected");
        }
    }
}
~~~

In the directory containing the file, run:

~~~bash
javac NumberLocaleDemo.java
java NumberLocaleDemo
~~~

Exact stdout:

~~~text
US_FORMAT=1,234.50
DE_FORMAT=1.234,50
US_PARSE=1234.50
DE_PARSE=1234.50
STRICT_PARSE=rejected
~~~

Explanation:
- `DecimalFormatSymbols.getInstance(locale)` retrieves the Locale-appropriate symbol set.
- The same non-localized pattern with different symbols produces different display strings.
- `setParseBigDecimal(true)` makes the parser return `BigDecimal`, avoiding conversion through `Double`.
- `ParsePosition` lets you check whether the parser consumed the entire string.
- `RoundingMode.HALF_EVEN` is chosen explicitly rather than relying on the reader remembering the default.

This is a standalone Java program, not a Spring formatter or web application. The following sections show how to plug formatting rules into Spring.

## 9. Registering number patterns in Spring MVC

### 9.1. Using @NumberFormat on a DTO

~~~java
public final class InvoiceForm {

    @NumberFormat(pattern = "#,##0.00")
    private BigDecimal amount;

    public BigDecimal getAmount() { return amount; }
    public void setAmount(BigDecimal amount) {
        this.amount = amount;
    }
}
~~~

In the controller:

~~~java
@PostMapping("/invoice")
public String submit(
        @Valid @ModelAttribute("invoice") InvoiceForm form,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return "invoice-form";
    }
    return "invoice-success";
}
~~~

This is an MVC integration snippet requiring controller setup, imports, views, and a validation provider. Spring MVC uses the configured `FormattingConversionService` in MVC to read the annotation. The request's Locale can be used when the formatter parses/prints.

### 9.2. Registering a formatter via WebMvcConfigurer

~~~java
@Configuration
public class WebConfig implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addFormatter(new NumberStyleFormatter("#,##0.00"));
    }
}
~~~

This is how to register a general formatter; determine which types the formatter supports and its scope of impact. If multiple fields need different patterns, annotations or property-specific formatters are usually clearer than a global formatter.

Do not create a standalone `FormattingConversionService` and assume Spring MVC automatically uses that instance. Register it using the appropriate MVC mechanism for your application version.

### 9.3. LocaleResolver and request locale

Spring MVC can determine the request's `Locale` via `LocaleResolver`/`LocaleContextResolver`. Formatters receive the `Locale` from the locale context during parse/print. Consequently, the same DTO and pattern can produce different strings depending on the request locale.

Establish agreement on:
- The default Locale when the client sends no preference.
- Accepted Locales and priority order.
- Input API Locale versus display Locale.
- How to handle strings that do not match the Locale.
- Whether Locale affects stored data or only presentation.

## 10. Separating conversion, formatting, and validation

| Stage | Example | Purpose |
| --- | --- | --- |
| Format/parse | `"1.234,50"` → `BigDecimal` 1234.50 under `de-DE` | Convert string to Java type |
| Validation | `@DecimalMin("0.00")` | Check thresholds |
| Domain logic | Money must have valid currency code and scale | Check business rules |
| Persistence | Store `DECIMAL` with designed precision/scale | Store numbers accurately |
| Presentation | `BigDecimal` → `"1.234,50"` by Locale | Display to users |

If a user enters `"0,00"` under `de-DE`: parsing may succeed as `BigDecimal.ZERO`; `@DecimalMin("0.01")` may reject it because the number is below the minimum. This is validation, not a format error.

If a user enters `"0,00 EUR"` while the formatter only accepts numbers, parsing may fail. If you want to accept currency symbols/units, you must use a formatter or model with an explicit currency and matching input contract.

## 11. Common pitfalls

1. **Treating pattern commas and periods as literal characters.** `DecimalFormat` patterns have their own syntax; Locale symbols control rendered characters.
2. **Swapping dots/commas with string replace.** This can corrupt `1,234` into the wrong number because you don't know which character is grouping vs decimal.
3. **Using a display Locale to parse an API.** APIs need a stable input contract; browser Locales can vary.
4. **Using Double for money requiring decimal precision.** Prefer `BigDecimal` and explicit scale/rounding rules.
5. **Including grouping separators in stored data.** Databases should store numbers, not formatted strings.
6. **Assuming pattern `0.00` validates exactly two input decimals.** Format patterns primarily control presentation; parsing can be looser than API requirements.
7. **Not checking the entire parsed string.** Use `ParsePosition` or a strict parser when trailing junk is disallowed.
8. **Confusing `12.5` with `12.5%`.** Percent patterns multiply the value; decide whether stored ratios are `0.125` or `12.5`.
9. **Using Locale to infer currency.** Currency codes must be explicit in the model/contract.
10. **Leaving rounding uncontrolled.** Choose `RoundingMode` in the domain rather than letting UI formatting decide business outcomes.
11. **Registering a global formatter without checking impact.** The same numeric type may be used on fields with different conventions.
12. **Assuming `@NumberFormat` is Bean Validation.** It guides formatting/parsing; min/max, scale, and business rules require dedicated validators.

## 12. Testing checklist

| Scenario | What Must Be Verified |
| --- | --- |
| Same `BigDecimal` formatted with `en-US` and `de-DE` | Grouping/decimal separators differ correctly |
| Parse `en-US` string with `de-DE` formatter | Does not silently misinterpret the number |
| Negative numbers with positive/negative pattern | Prefix/suffix are correct |
| Patterns `0.00` and `#,##0.##` | Trailing zeros and fraction digits are correct |
| Percent pattern | Stored and displayed values are not multiplied twice |
| Number with too many fraction digits | Rounding or rejection rule is clear |
| String with trailing characters | Strict parser rejects it |
| Empty/null | Optionality and validation policy are correct |
| Changing request Locale | Parse/print follows published contract |
| Currency | Amount and currency code are not inferred |
| `@NumberFormat` on DTO | Annotation is read in MVC `FormattingConversionService` |
| Global formatter | No unintended side effects on other fields |

## 13. Official documentation

- [Spring Field Formatting Reference](https://docs.spring.io/spring-framework/reference/core/validation/format.html): NumberStyleFormatter, CurrencyStyleFormatter, PercentStyleFormatter, @NumberFormat, and Locale.
- [@NumberFormat Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/format/annotation/NumberFormat.html): pattern and style.
- [NumberStyleFormatter Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/format/number/NumberStyleFormatter.html): NumberFormat-based number formatter.
- [Java 17 DecimalFormat Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormat.html): pattern, symbols, grouping, rounding, and parsing.
- [Java 17 DecimalFormatSymbols Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormatSymbols.html): decimal/grouping separators and other symbols.
- [Spring MVC Formatting Configuration](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/conversion.html): registering Formatters and Converters in MVC.

**Core principle:** patterns define numeric structure; Locale supplies regional symbols and conventions; `BigDecimal` holds numeric values; validation and domain logic verify business validity. Specify the Locale for both parsing and printing, validate the full string when strictness is required, and keep rounding/scale in the appropriate business layer.