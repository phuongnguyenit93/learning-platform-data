# @NumberFormat for Number, Currency, or Percent Styles in Spring Framework

## 1. What problem does @NumberFormat solve?

A numeric value in Java is typically stored in a machine-friendly type such as `Integer`, `Long`, `BigDecimal`, or `Double`. When displayed to users, the same value may need multiple formatting representations:

- Standard numbers: `1234567.5` may be displayed as `1,234,567.5` in the US locale or `1.234.567,5` in many European locales.
- Currency: `1234.5` may be displayed as `$1,234.50`, `1.234,50 €`, or another format depending on locale/currency.
- Percent: a ratio value `0.125` is typically displayed as `12.5%`.

Spring provides the `org.springframework.format.annotation.NumberFormat` annotation to declare **how a number is presented on a field/property/parameter**. The formatting infrastructure reads this annotation and selects the corresponding formatter to convert between the string representation and the numeric type value.

Example:

```java
public class InvoiceForm {

    @NumberFormat(style = NumberFormat.Style.NUMBER)
    private BigDecimal quantity;

    @NumberFormat(style = NumberFormat.Style.CURRENCY)
    private BigDecimal total;

    @NumberFormat(style = NumberFormat.Style.PERCENT)
    private BigDecimal taxRate;
}
```

For the three properties above, the Java values remain numeric. The annotation only describes how to parse/print when Spring performs conversion in a context that supports field formatting. `@NumberFormat` **does not turn a field into a String**, does not automatically change the database schema, and is not a validation rule.

## 2. The three styles: NUMBER, CURRENCY, and PERCENT

`NumberFormat.Style` defines three primary options:

| Style | Purpose | Spring Formatter |
| --- | --- | --- |
| `NUMBER` | Standard decimal number, with locale-specific grouping/decimal separators | `NumberStyleFormatter` |
| `CURRENCY` | Displays a number according to the locale's currency style | `CurrencyStyleFormatter` |
| `PERCENT` | Displays a number as a percentage | `PercentStyleFormatter` |

Example with the US locale and `BigDecimal("1234.5")`:

| Java Value | Style | Illustrative Display Format |
| --- | --- | --- |
| `1234.5` | `NUMBER` | `1,234.5` |
| `1234.5` | `CURRENCY` | `$1,234.50` |
| `0.125` | `PERCENT` | `12.5%` |

These results depend on the locale and JDK formatting rules. Different locales may change grouping separators, decimal separators, currency symbol placement, and whitespace. You should not hardcode a formatted currency string as a business value.

### NUMBER

Used for counts, quantities, scores, coefficients, or values without monetary meaning. The default formatter uses locale-based number style rules. A pattern can be configured to determine the number of decimal digits, grouping, and display format.

### CURRENCY

Used when you want to display a value as currency. `CurrencyStyleFormatter` relies on the locale's currency formatting, including symbol, separators, and decimal digits according to the currency format. The annotation does not automatically determine the business currency of an account or transaction; it uses the current locale's rules unless the application configures it further.

**Do not use the currency style as a currency conversion mechanism.** Formatting `BigDecimal("100")` into a locale's currency unit does not mean the number 100 has been converted from USD to VND or vice versa. Exchange rates, currency codes, and rounding rules belong to dedicated domain currency logic.

### PERCENT

Used for ratios such as tax rates, completion rates, discount rates, or probabilities. A percent formatter typically multiplies the ratio by 100 when printing and converts the percentage string back to a ratio value when parsing.

For example, `BigDecimal("0.125")` is displayed as `12.5%` in the US locale. When parsing `"12.5%"`, the resulting numeric value is `0.125` (not `12.5`). Keep this in mind when data stored in the database or API uses decimal ratios.

## 3. Declaring the annotation and its attributes

Basic syntax:

```java
import java.math.BigDecimal;
import org.springframework.format.annotation.NumberFormat;

public class ProductForm {

    @NumberFormat(style = NumberFormat.Style.NUMBER)
    private BigDecimal quantity;

    @NumberFormat(style = NumberFormat.Style.CURRENCY)
    private BigDecimal price;

    @NumberFormat(style = NumberFormat.Style.PERCENT)
    private BigDecimal discountRate;
}
```

`@NumberFormat` has two important attributes:

| Attribute | Meaning | Default |
| --- | --- | --- |
| `style` | Selects `NUMBER`, `CURRENCY`, or `PERCENT` | `NUMBER` |
| `pattern` | DecimalFormat-style number formatting pattern | Empty string, meaning `style` is used |

You can write:

```java
@NumberFormat
private BigDecimal amount;
```

This is equivalent to using `style = NumberFormat.Style.NUMBER` when no pattern is declared.

### Pattern takes precedence over style

If `pattern` is non-empty, Spring creates `NumberStyleFormatter(pattern)`. In that case, the pattern acts as the direct rule, overriding the default formatter selected by `style`.

Example:

```java
@NumberFormat(pattern = "#,##0.00")
private BigDecimal unitPrice;

@NumberFormat(pattern = "0.000")
private BigDecimal exchangeFactor;
```

The pattern `#,##0.00` requires grouping and two decimal digits; `0.000` requires three decimal digits. Patterns are based on `DecimalFormat` syntax. A pattern does not automatically add a currency code, determine exchange rates, or validate business ranges.

Do not specify both `style = CURRENCY` and an arbitrary pattern expecting Spring to combine the two rules. When a pattern is declared, the pattern formatter is used. If you need currency representation with custom rules, design an appropriate pattern/formatter or use a monetary model with an explicit currency.

## 4. How does Spring process @NumberFormat?

The annotation does not run on its own. The formatting infrastructure must be configured and invoked along the appropriate conversion path.

In Spring, `NumberFormatAnnotationFormatterFactory` is the component that connects the `@NumberFormat` annotation to formatters. The factory provides support for common numeric types such as:

- `Short`, `Integer`, `Long`.
- `Float`, `Double`.
- `BigDecimal`, `BigInteger`.

The factory reads the annotation:

1. If `pattern` is non-empty, create `NumberStyleFormatter(pattern)`.
2. If there is no pattern and `style` is `PERCENT`, create `PercentStyleFormatter`.
3. If `style` is `CURRENCY`, create `CurrencyStyleFormatter`.
4. Otherwise, use `NumberStyleFormatter`.

`DefaultFormattingConversionService` registers the formatter factory for `@NumberFormat` in its default set. Spring MVC also installs common number formatters and supports this annotation in its conversion/formatting infrastructure.

Flow:

```text
String from form/request or Number in model
                    |
                    v
     FormattingConversionService
                    |
                    v
       read TypeDescriptor/property
                    |
                    v
       detect @NumberFormat
                    |
                    v
 NumberFormatAnnotationFormatterFactory
                    |
          +---------+---------+
          |         |         |
          v         v         v
        NUMBER   CURRENCY   PERCENT
          |         |         |
          v         v         v
      NumberStyle CurrencyStyle PercentStyle
       Formatter    Formatter   Formatter
          |         |         |
          +---------+---------+
                    |
                    v
       parse String <-> Number
                    |
                    v
        property / view / form
```

`TypeDescriptor` lets Spring know which property/parameter carries the annotation and what the concrete numeric type is. Calling a formatter with only a raw class without property metadata cannot be expected to tell Spring which field to read the annotation from.

## 5. How Locale affects the result

Number formatting is a locale-dependent operation. The same Java value `1234.5` can be represented differently:

| Locale | Example Number | Example Currency |
| --- | --- | --- |
| `en-US` | `1,234.5` | `$1,234.50` |
| `de-DE` | `1.234,5` | EUR format according to German rules |
| `vi-VN` | Vietnamese number punctuation rules | VND format according to Vietnamese rules |

The table only illustrates locale differences and is not a fixed string contract across all JDK/CLDR versions. You must use the request/user locale and test on the deployment environment.

In Spring, the formatter receives a `Locale` when parsing/printing. A web request can use a locale resolver/interceptor to determine the current locale. In code without a web context, you can supply the locale when calling the formatter directly or set `LocaleContextHolder` for the appropriate conversion flow.

Example in Spring MVC:

```java
@Configuration
public class WebConfig implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        // Application-specific Formatter/Converter can be registered here.
    }
}
```

This is an extension configuration when custom behavior is needed. For standard `@NumberFormat`, Spring MVC already provides default support in the formatting conversion service; there is no need to manually re-register the formatter factory in every controller.

**Locale is not a currency setting.** Locale determines regional/language display rules, including the default currency format. For financial applications supporting multiple currencies, store the currency code separately (for example ISO 4217) and do not infer the transaction currency solely from the user's locale.

## 6. Runnable Java 17+ example: formatting three number styles

This example uses Spring Framework 6.2.x, Java 17+, and Maven. It uses `DefaultFormattingConversionService` to demonstrate annotations on properties being used for both formatting and parsing. For predictable output, the example sets the locale to `Locale.US` at runtime.

### 6.1. Maven dependency

Create `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
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
            <version>6.2.12</version>
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

`spring-context` pulls in the Spring Core/Beans modules needed for the formatting service. The example does not require Spring Boot or an HTTP server.

### 6.2. Complete Java class

Create `src/main/java/demo/NumberFormatDemo.java`:

```java
package demo;

import java.lang.reflect.Field;
import java.math.BigDecimal;
import java.util.Locale;

import org.springframework.core.convert.TypeDescriptor;
import org.springframework.format.annotation.NumberFormat;
import org.springframework.format.support.DefaultFormattingConversionService;
import org.springframework.context.i18n.LocaleContextHolder;

public class NumberFormatDemo {

    public static class Invoice {
        @NumberFormat(style = NumberFormat.Style.NUMBER)
        private BigDecimal quantity = new BigDecimal("1234.5");

        @NumberFormat(style = NumberFormat.Style.CURRENCY)
        private BigDecimal amount = new BigDecimal("1234.5");

        @NumberFormat(style = NumberFormat.Style.PERCENT)
        private BigDecimal taxRate = new BigDecimal("0.125");
    }

    private static String print(
            DefaultFormattingConversionService service,
            Invoice invoice,
            String fieldName) throws NoSuchFieldException {

        Field field = Invoice.class.getDeclaredField(fieldName);
        TypeDescriptor descriptor = new TypeDescriptor(field);
        BigDecimal value = (BigDecimal) descriptor.getType()
                .cast(readValue(invoice, fieldName));

        return (String) service.convert(
                value,
                descriptor,
                TypeDescriptor.valueOf(String.class));
    }

    private static Object readValue(
            Invoice invoice, String fieldName) {
        return switch (fieldName) {
            case "quantity" -> invoice.quantity;
            case "amount" -> invoice.amount;
            case "taxRate" -> invoice.taxRate;
            default -> throw new IllegalArgumentException(fieldName);
        };
    }

    private static BigDecimal parse(
            DefaultFormattingConversionService service,
            String fieldName,
            String text) throws NoSuchFieldException {

        Field field = Invoice.class.getDeclaredField(fieldName);
        TypeDescriptor target = new TypeDescriptor(field);

        return (BigDecimal) service.convert(
                text,
                TypeDescriptor.valueOf(String.class),
                target);
    }

    public static void main(String[] args) throws Exception {
        LocaleContextHolder.setLocale(Locale.US);
        try {
            DefaultFormattingConversionService service =
                    new DefaultFormattingConversionService();
            Invoice invoice = new Invoice();

            String number = print(service, invoice, "quantity");
            String currency = print(service, invoice, "amount");
            String percent = print(service, invoice, "taxRate");

            System.out.println("number=" + number);
            System.out.println("currency=" + currency);
            System.out.println("percent=" + percent);

            System.out.println("parsedAmount="
                    + parse(service, "amount", currency).toPlainString());
            System.out.println("parsedRate="
                    + parse(service, "taxRate", percent).toPlainString());
        } finally {
            LocaleContextHolder.resetLocaleContext();
        }
    }
}
```

In this demo, `TypeDescriptor` is created directly from the annotated field. When converting from `BigDecimal` to `String`, Spring inspects the annotation on the source property descriptor and selects the appropriate formatter. When parsing a `String` back to `BigDecimal`, the target field's descriptor provides the annotation to the parser.

### 6.3. Compile, run, and output

In the directory containing `pom.xml`, run:

```bash
mvn -q compile
mvn -q org.codehaus.mojo:exec-maven-plugin:3.5.1:java -Dexec.mainClass=demo.NumberFormatDemo
```

With Spring 6.2.x, JDK 17+, and locale `en-US`, the expected output from the program is:

```text
number=1,234.5
currency=$1,234.50
percent=12.5%
parsedAmount=1234.50
parsedRate=0.125
```

Explanation:

- `quantity` uses `NUMBER`, so it formats thousands grouping and the decimal separator.
- `amount` uses `CURRENCY`, displaying the currency symbol and two decimal digits of USD in the US locale.
- `taxRate` stores `0.125`, which prints as `12.5%`.
- Parsing the currency string back yields `BigDecimal`, without turning it into a business `String`.
- Parsing the percentage `12.5%` returns the ratio `0.125`.

The example deliberately uses `BigDecimal` to preserve decimal precision. For monetary use cases, avoid using `double` for values requiring exact calculation.

## 7. Using @NumberFormat in Spring MVC forms

In Spring MVC, string request parameters are bound to model attributes. The formatting conversion infrastructure reads `@NumberFormat` on properties to parse values and format them back when rendering the form/view.

Model example:

```java
package demo.web;

import java.math.BigDecimal;
import org.springframework.format.annotation.NumberFormat;

public class PriceForm {

    @NumberFormat(style = NumberFormat.Style.CURRENCY)
    private BigDecimal unitPrice;

    @NumberFormat(style = NumberFormat.Style.PERCENT)
    private BigDecimal discountRate;

    public BigDecimal getUnitPrice() { return unitPrice; }
    public void setUnitPrice(BigDecimal unitPrice) {
        this.unitPrice = unitPrice;
    }

    public BigDecimal getDiscountRate() { return discountRate; }
    public void setDiscountRate(BigDecimal discountRate) {
        this.discountRate = discountRate;
    }
}
```

Controller:

```java
@Controller
public class PriceController {

    @PostMapping("/price")
    public String submit(
            @Valid @ModelAttribute("priceForm") PriceForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return "price-form";
        }
        return "price-result";
    }
}
```

This is a controller template that requires Spring MVC imports, Jakarta Validation if `@Valid` is used, and the corresponding views. `BindingResult` must immediately follow the model attribute parameter to receive binding/validation errors. You do not need to call `NumberFormatAnnotationFormatterFactory` manually in the controller; the default infrastructure handles the annotation automatically.

A form field is submitted as a string according to the active locale. If the locale is `en-US`, currency input can be in the form `$1,234.50`; with another locale, separators and symbols may differ. Forms should render values using the same locale that the server uses to parse them. If the client sends a string in a locale different from the request locale, parsing may fail.

### Rendering values in the view

With template engines, you can display formatted properties directly via their corresponding integration or use the view's formatter/conversion service. The exact mechanism depends on Thymeleaf, JSP, FreeMarker, or whichever template engine is in use. Do not assume every expression engine automatically invokes `@NumberFormat` simply because the model property has the annotation; verify the integration and rendering behavior of your framework/view technology.

## 8. When to choose pattern instead of style?

Use `style` when standard locale-based rules are sufficient. Use `pattern` if display requirements mandate a specific number of digits or grouping.

Example:

```java
@NumberFormat(pattern = "#,##0")
private BigDecimal wholeUnits;

@NumberFormat(pattern = "#,##0.000")
private BigDecimal preciseRate;

@NumberFormat(pattern = "0.00")
private BigDecimal shortDisplay;
```

Some common patterns:

| Pattern | Meaning |
| --- | --- |
| `#,##0` | Integer with grouping |
| `#,##0.00` | Two decimal digits |
| `0.000` | Three decimal digits, no mandatory grouping |
| `#,##0.###` | Up to three decimal digits |
| `000000` | Left-padded with zeros to six digits |

Patterns are interpreted by `DecimalFormat`, so characters like `0`, `#`, grouping separators, and decimal separators have specific meanings. The actual separator characters still depend on the locale when the formatter creates the format instance.

**A pattern is not a regex and not a validation annotation.** A pattern controls how numbers are parsed/printed. To require values within a range, use Bean Validation such as `@DecimalMin`/`@DecimalMax` or check business rules in the service layer.

## 9. Which numeric types does @NumberFormat support?

Spring's default factory supports common wrapper/number types such as `Short`, `Integer`, `Long`, `Float`, `Double`, `BigDecimal`, and `BigInteger`. Primitive types can be supported through the conversion framework's primitive/wrapper handling, though when a value may be null, wrapper/reference types are usually clearer.

Do not assume the annotation applies directly to custom types, such as `Money` or `Quantity`, simply because they contain a `BigDecimal` internally. For custom domain types, write an appropriate `Formatter`/`Converter` or expose an actual numeric property for the annotation to handle.

For monetary values, `BigDecimal` is suitable for decimal amounts, but it does not carry a currency code. A class like `Money(amount, currency)` represents the domain more completely. A specialized formatter may need to read the currency code rather than relying solely on the locale's default currency.

## 10. How @NumberFormat differs from @Digits, @DecimalMin, and validation

This is a common point of confusion:

| Annotation | Role |
| --- | --- |
| `@NumberFormat` | Rules for formatting/parsing numbers |
| `@Digits(integer=..., fraction=...)` | Limits integer/fraction digit counts in validation |
| `@DecimalMin("0.01")` | Minimum value constraint in validation |
| `@DecimalMax("100")` | Maximum value constraint in validation |
| `@Positive` / `@PositiveOrZero` | Sign constraint on the value |
| `@NotNull` | Value is required |

They can be combined:

```java
@NumberFormat(style = NumberFormat.Style.CURRENCY)
@NotNull
@DecimalMin("0.01")
private BigDecimal price;
```

`@NumberFormat` converts representations; validation annotations check the value after binding. For validation to run, a Jakarta Bean Validation provider and an activation mechanism such as `@Valid`/`@Validated` are required. Simply adding `@NumberFormat` will not reject negative values or turn empty strings into business errors.

## 11. Registering a custom formatter

When the three default styles are not enough, you can register a `Formatter<Number>` or `Converter` in `FormatterRegistry`.

MVC configuration example:

```java
@Configuration
public class NumberFormattingConfig implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addFormatterForFieldType(
                BigDecimal.class, new CustomMoneyFormatter());
    }
}
```

This snippet requires your application's `CustomMoneyFormatter` class and corresponding imports. It registers a formatter for the `BigDecimal` field type in this registry; if multiple `BigDecimal` properties have different formatting rules, a type-wide formatter may be too broad. Consider an annotation-specific `AnnotationFormatterFactory` or a dedicated domain type.

`DefaultFormattingConversionService` is an option for non-MVC code; the `FormattingConversionService` in MVC is configured in the application context. Creating a local formatter service will not cause Spring MVC to automatically use that instance.

## 12. Precision, rounding, and currency

Key considerations when handling money:

- Use `BigDecimal` instead of `double`/`float` in calculations requiring decimal precision.
- Initialize from strings, e.g., `new BigDecimal("19.95")`, rather than `new BigDecimal(19.95)` to avoid carrying binary floating-point inaccuracies from `double` into decimal values.
- Distinguish between stored values and display formatting: displaying two decimal digits does not mean the underlying value has been rounded/saved to two digits.
- Define rounding policies in the business/service or monetary layer, rather than relying on text formatting.
- Store the currency code alongside the amount when the domain supports multiple currencies.
- Do not directly add or subtract amounts in different currencies without converting them according to business rules.
- Verify database scale/precision limits and API serialization formats.

Example:

```java
BigDecimal amount = new BigDecimal("19.955");
BigDecimal rounded = amount.setScale(
        2, RoundingMode.HALF_UP);
```

This performs actual data rounding. It is different from merely displaying `19.955` as a two-decimal string through a formatter. Choose an explicit rounding mode based on business regulations and currency type; there is no single rounding rule suitable for every system.

## 13. Common errors and troubleshooting

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| Annotation has no effect on display | Conversion service lacks `NumberFormat` formatter factory or does not use property `TypeDescriptor` | Use the appropriate `FormattingConversionService`; verify the descriptor |
| `@NumberFormat` treated as validation | Confusing formatting with value checking | Use Bean Validation for range/digit constraints |
| Parses on one machine, fails on another | Different locales | Explicitly specify request/test locale |
| Unexpected currency symbol | Active locale has a different default currency | Manage business currency codes separately |
| Percent displays 100x larger than expected | Storing `12.5` instead of ratio `0.125` | Standardize on storing decimal ratios |
| Wrong decimal separator | Input string uses a different locale | Synchronize form and server locales |
| Precision loss after parsing | Using `Float`/`Double` or manually parsing as `double` | Use `BigDecimal` and an appropriate formatter |
| Pattern does not behave like the desired style | Non-empty `pattern` takes precedence over `style` | Choose one primary rule |
| Empty string yields `null` | Conversion/editor may map empty input to `null` | Enforce required validation separately |
| `@RequestBody` JSON does not use annotation like forms | JSON goes through Jackson `HttpMessageConverter` | Configure Jackson when JSON formatting is needed |
| Direct `canConvert`/formatting differs from MVC | Different locale/context or descriptor | Test through the actual MVC request path |
| Field annotation is not found | Conversion called via class-only overload, missing property descriptor | Pass the field/parameter `TypeDescriptor` |

### Debugging workflow

1. Check the actual Java type of the property and the annotation on the field/getter/parameter.
2. Verify whether the conversion path goes through `FormattingConversionService`.
3. Check whether `TypeDescriptor` preserves the annotation.
4. Determine the current `Locale` of the request.
5. Test printing and parsing separately with data containing grouping separators, currency symbols, and percent signs.
6. Inspect `BindingResult` during form binding; distinguish type mismatches from validation failures.
7. Check the JSON converter separately if the error only occurs with `@RequestBody`.

## 14. Meaningful testing

A test suite should cover:

| Test | Value | What to Verify |
| --- | --- | --- |
| NUMBER format | `1234.5` | Locale-specific grouping/decimal separators |
| CURRENCY format | `1234.5` | Locale-specific symbol and decimal digits |
| PERCENT format | `0.125` | Prints `12.5%`, parses back to `0.125` |
| Custom pattern | `1234.5678` | Displayed digits match the pattern |
| Locale switching | `en-US` and `de-DE` | Separators/formats differ appropriately |
| Invalid input | `"abc"` | Binding/conversion error |
| Validation range | negative number with `@DecimalMin` | Binding may succeed, validation fails |
| BigDecimal precision | long decimal string | No unintended precision loss |

When testing locales, set the locale explicitly and restore the context after the test; do not let one test's locale leak into the next. For Spring MVC, include `MockMvc` integration tests to confirm request parameters are parsed according to the configured locale.

## 15. Project usage checklist

1. Choose the right numeric type: `Integer`/`Long` for integers; `BigDecimal` for decimals and money.
2. Choose `NUMBER`, `CURRENCY`, or `PERCENT` style matching the property's meaning.
3. If a specific format is needed, declare `pattern` and remember `pattern` takes precedence.
4. Determine the request/user locale; do not assume the server locale is the business locale.
5. Keep percentage ratios consistently as decimals, e.g., `0.125` for `12.5%`.
6. For multi-currency systems, store amount and currency code separately.
7. Verify `FormattingConversionService` is used in MVC or the actual code path.
8. Use separate validation for required/range/precision constraints.
9. Test bidirectional formatting and parsing across all supported locales.
10. Never rely on formatted display strings for calculations or currency conversion.

## 16. Summary

`@NumberFormat` declares how Spring **parses and prints numeric types** during formatting conversion. `NUMBER` uses the number style, `CURRENCY` uses the currency style, and `PERCENT` uses the percent style. If `pattern` is non-empty, a pattern-based formatter is created instead of the default style formatter. Results depend on the locale; percentages are stored as decimal ratios, and currency style does not automatically convert or determine the business currency code.

The annotation takes effect when data flows through the formatting infrastructure with proper property metadata. In Spring MVC, default number formatters and `@NumberFormat` support are already configured. To validate ranges, digit counts, or required values, use Bean Validation; when handling money, use `BigDecimal`, explicit currency codes, and a clear rounding policy.

## Official references

- [Spring Framework 6.2 — Field Formatting](https://docs.spring.io/spring-framework/reference/6.2/core/validation/format.html)
- [Spring Framework 6.2 — MVC Type Conversion](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/conversion.html)
- [NumberFormat API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/format/annotation/NumberFormat.html)
- [NumberFormatAnnotationFormatterFactory API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/format/number/NumberFormatAnnotationFormatterFactory.html)
- [NumberStyleFormatter API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/format/number/NumberStyleFormatter.html)
- [CurrencyStyleFormatter API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/format/number/CurrencyStyleFormatter.html)
- [PercentStyleFormatter API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/format/number/PercentStyleFormatter.html)
- [DefaultFormattingConversionService API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/format/support/DefaultFormattingConversionService.html)
