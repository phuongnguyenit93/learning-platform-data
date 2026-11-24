# Currency, Units, and Allowed Input Data in Spring Formatting

When a form accepts prices, quantities, or measured amounts, an application must solve three distinct problems:

1. **Formatting:** displaying a value by locale, e.g., `1,234.50 $` or `1.234,50 $`; parsing user-entered strings into Java types.
2. **Modeling currency/units:** storing monetary amounts alongside their currency code and measurements alongside their unit, rather than keeping an uncontextualized raw number.
3. **Controlling allowed input:** restricting currency codes/units, digit counts, value ranges, and business rules.

In Spring Framework, `Formatter<T>` combines `Parser<T>` and `Printer<T>` to convert String ⇄ object by `Locale`. `@NumberFormat` provides number/currency formatting by style or pattern. `Formatter` and `@NumberFormat` assist with **parsing and presentation**; they do not replace validation, allowlists, or authorization.

This article covers choosing data types, formatting currency, handling units, registering formatters, and restricting input; it includes a runnable Java 17+ example with Maven and Spring MVC integration.

## 1. Separating four concepts

| Concept | Question | Example |
| --- | --- | --- |
| **Numeric value** | How much? | `1234.50` |
| **Currency** | Which currency does the amount belong to? | `EUR`, `USD`, `VND` |
| **Unit of measure** | In which unit is the quantity measured? | `kg`, `g`, `L`, `m` |
| **Input rules** | Which values are accepted? | `amount > 0`; currency only accepts `USD/EUR/VND` |

Symbols like `$`, `€`, or `₫` should not be treated as a reliable currency identifier. Symbols can overlap, vary by locale, and do not always indicate the exact ISO code. For example, `$` can mean USD, CAD, AUD, or several others depending on context.

Similarly, the number `10` lacks clear meaning without a unit: 10 kg differs from 10 g; 10 liters differs from 10 ml.

**A good model stores data separately:**

~~~text
Money
  amount   = BigDecimal("1234.50")
  currency = Currency("EUR")

Quantity
  amount   = BigDecimal("2.5")
  unit     = "kg"
~~~

The presentation layer formats these into user-appropriate strings. Stored data and business logic should not depend on which commas, periods, spaces, or currency symbols the user sees.

## 2. Why should currency use BigDecimal?

Currency is numeric data requiring precision control. For decimal values, do not use `float` or `double` as primary monetary storage/calculation types because binary floating-point types cannot represent all decimal numbers accurately.

Example:

~~~java
System.out.println(0.1 + 0.2);
System.out.println(new BigDecimal("0.1").add(new BigDecimal("0.2")));
~~~

Illustrative output:

~~~text
0.30000000000000004
0.3
~~~

Use `new BigDecimal("0.1")` or construct from exact decimal data; avoid `new BigDecimal(0.1)` because binary error from `double` enters the `BigDecimal` value immediately.

### Minimal Money model

~~~java
public record Money(BigDecimal amount, Currency currency) {
}
~~~

This is an illustrative record requiring `java.math.BigDecimal` and `java.util.Currency`. It holds both the amount and the currency code. Two amounts `10 USD` and `10 EUR` must never be treated as equal monetary values simply because both have an amount of 10.

In a complete design, decide:

- Are negative amounts allowed (e.g., refunds, adjustment entries)?
- What precision/scale is acceptable per currency?
- What is the rounding rule for taxes, splitting amounts, or conversion?
- Can two amounts with different currencies be added? Usually the same currency or an explicit FX workflow is required.
- Are there minimum and maximum amount limits in the business layer?

`BigDecimal` does not automatically know a currency's scale rules. `Currency.getDefaultFractionDigits()` provides default decimal digits from JDK currency metadata, though business logic must still decide rounding and exceptions. Do not assume every currency has two decimal digits.

## 3. Locale and Currency are two different things

`Locale` describes language/regional conventions, such as number notation and symbol placement. `Currency` identifies a concrete monetary unit, such as `EUR` or `USD`.

| Locale | Currency | Possible Display Format |
| --- | --- | --- |
| `Locale.US` | USD | `$1,234.50` |
| `Locale.GERMANY` | EUR | `1.234,50 €` |
| `Locale.FRANCE` | EUR | `1 234,50 €` |
| `Locale.US` | EUR | `€1,234.50` or formatter/JDK-dependent form |

The column above shows locale/JDK formatting examples; exact symbol placement and whitespace can vary across runtime versions. **Locale does not determine the transaction currency.** Someone in Germany can buy in USD; someone in the US can pay in EUR.

For an actual monetary amount, determine the currency from the transaction contract or trusted server data. Do not infer stored currency solely from the server's `Locale.getDefault()`.

If a client sends `currency=USD`, the application must check whether that currency is permitted for the current operation, account, product, and user.

## 4. @NumberFormat: formatting numbers and currency in Spring

Spring provides `org.springframework.format.annotation.NumberFormat` for `Number` fields such as `Integer`, `Long`, `Double`, and `BigDecimal`.

Example:

~~~java
public class InvoiceForm {

    @NumberFormat(style = NumberFormat.Style.CURRENCY)
    private BigDecimal unitPrice;

    @NumberFormat(pattern = "#,##0.000")
    private BigDecimal quantity;

    // Getters/setters...
}
~~~

This is an **illustrative class snippet**; it requires Spring annotation imports, `java.math.BigDecimal`, and appropriate getters/setters. `@NumberFormat` has two main configuration options:

- `style`: selects common number styles such as `DEFAULT`, `NUMBER`, `PERCENT`, or `CURRENCY`.
- `pattern`: specifies a concrete number formatting pattern.

The `style` and `pattern` attributes are alternatives; when `pattern` is specified, `pattern` takes precedence. Style formatting relies on the user/context locale. Spring Javadoc notes that monetary types may default to currency style where applicable; applications should test the exact field type and runtime.

### @NumberFormat does not turn BigDecimal into Money

If a field is `BigDecimal` and annotated with `@NumberFormat(style=CURRENCY)`, the formatter knows **how to format the number using the locale's currency style**. It does not add a `Currency` property to the object and does not guarantee knowledge of the specific transaction currency.

For domain models that must carry currency codes, define a `Money(amount, currency)` object and a dedicated formatter/converter for that type. `@NumberFormat` can be used on an amount when currency is already fixed by a trusted data source and display rules are clear.

### Choosing patterns intentionally

For instance, `pattern="#,##0.00"` can enforce two decimal digits in presentation per `DecimalFormat` rules. Yet a pattern does not solve business rules such as:

- Is entering more than two decimal digits allowed?
- Should input be rounded or rejected?
- Does this currency have 0 or 3 fraction digits?
- Are negative numbers accepted?

Define input and storage rules separately. Format patterns are primarily presentation/parsing rules.

## 5. Units of measure: more than a display suffix

A measured quantity should be paired with an explicit unit:

~~~java
public record Quantity(BigDecimal value, String unit) {
}
~~~

This is an illustrative type. Storing only `BigDecimal value` leaves the system unable to tell whether that number is kg, g, L, ml, or another quantity.

A better modeling approach is using an enum for **system-supported units**:

~~~java
public enum MassUnit {
    KG, G
}
~~~

With a unit enum, external input must be parsed against an allowlist:

~~~java
MassUnit unit = MassUnit.valueOf(input.toUpperCase(Locale.ROOT));
~~~

This is a short snippet requiring `java.util.Locale`. In real applications, catch `IllegalArgumentException` or use a parser that returns meaningful errors. Do not accept arbitrary strings as units because that creates data that cannot be calculated or compared consistently.

### Unit conversions must be defined

Mass example:

- `1 kg = 1000 g`
- `1 g = 0.001 kg`

Two quantities `500 g` and `0.5 kg` represent the same physical mass despite different strings. To compare or sum them, convert to a canonical unit before computing or use a unit-of-measure library with clear dimension/quantity definitions.

Never add `2 kg + 300 g` by adding raw numbers to get 302. Convert `300 g` to `0.3 kg` first.

**Incompatible dimensions:** kg cannot convert to liters without density/material metadata; meters cannot be added to kg. Data types and domain APIs should prevent such nonsensical operations.

### A Formatter can be used per Quantity type

A formatter can parse `"2.5 kg"` into `Quantity(value=2.5, unit=KG)`, provided you define:

- Which decimal separator the locale uses?
- Is unit casing flexible?
- Is whitespace mandatory between number and unit?
- Are units outside the allowlist allowed?
- Does the printer output technical codes (`kg`) or localized names (`kilogram`)?

Separating number parsing from unit parsing is easier to test than a complex regex. For larger requirements, consider a dedicated unit-of-measure library instead of building a general-purpose unit engine from scratch.

## 6. Formatting Money with Formatter<T>

To make currency and locale explicit, let's implement `Formatter<Money>` with these rules:

- `Money` holds `BigDecimal amount` and `Currency currency`.
- The formatter is created with **a fixed currency** for a predetermined field/transaction.
- Users enter the numeric portion, e.g., `1,234.50` in the US locale; the string does not require a currency symbol.
- The printer displays the currency symbol according to locale, while the currency comes from domain configuration.
- Locale is never used to decide which currencies are allowed.

Accepting the amount without a symbol in the example is intentional: it avoids ambiguity when the `$` symbol can stand for multiple currencies.

### 6.1. Complete formatter code

~~~java
package example;

import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Currency;
import java.util.Locale;

import org.springframework.format.Formatter;

public final class MoneyFormatter implements Formatter<MoneyFormatter.Money> {

    public record Money(BigDecimal amount, Currency currency) {
    }

    private final Currency currency;

    public MoneyFormatter(Currency currency) {
        this.currency = currency;
    }

    @Override
    public Money parse(String text, Locale locale) {
        if (text == null || text.isBlank()) {
            throw new IllegalArgumentException("Amount is required");
        }

        NumberFormat numberFormat = NumberFormat.getNumberInstance(locale);
        if (!(numberFormat instanceof DecimalFormat decimalFormat)) {
            throw new IllegalStateException(
                    "This example requires DecimalFormat");
        }

        decimalFormat.setParseBigDecimal(true);
        ParsePosition position = new ParsePosition(0);
        Number parsed = decimalFormat.parse(text.trim(), position);

        if (!(parsed instanceof BigDecimal amount)
                || position.getErrorIndex() >= 0
                || position.getIndex() != text.trim().length()) {
            throw new IllegalArgumentException(
                    "Amount is not valid for locale " + locale);
        }

        return new Money(amount, currency);
    }

    @Override
    public String print(Money money, Locale locale) {
        if (money == null) {
            return "";
        }
        if (!currency.equals(money.currency())) {
            throw new IllegalArgumentException("Unexpected currency");
        }

        NumberFormat format = NumberFormat.getCurrencyInstance(locale);
        format.setCurrency(currency);
        return format.format(money.amount());
    }
}
~~~

This is a complete formatter class. In Java 17, pattern matching with `instanceof DecimalFormat decimalFormat` works directly. `DecimalFormat#setParseBigDecimal(true)` parses to `BigDecimal` instead of losing precision via `double`. `ParsePosition` is checked to avoid accepting partially parsed strings.

Several design decisions in this example are important to understand:

- Currency is passed to the constructor, not extracted from currency symbols in text.
- The parser only accepts locale-formatted numeric strings; if clients should select currency, parse the ISO code separately and check an allowlist.
- The printer verifies that `Money`'s currency matches the formatter's currency; it never silently prints a EUR amount as if it were USD.
- The example uses JDK `NumberFormat`/`DecimalFormat`; invalid data is rejected. Exact grouping-separator acceptance still depends on locale and JDK, so test boundary strings on the real runtime.

### 6.2. Runnable round-trip verification program

Create `src/main/java/example/MoneyFormattingDemo.java`:

~~~java
package example;

import java.math.BigDecimal;
import java.util.Currency;
import java.util.Locale;

import org.springframework.format.support.DefaultFormattingConversionService;

public class MoneyFormattingDemo {

    public static void main(String[] args) {
        Currency eur = Currency.getInstance("EUR");
        MoneyFormatter formatter = new MoneyFormatter(eur);

        MoneyFormatter.Money money =
                formatter.parse("1,234.50", Locale.US);

        String us = formatter.print(money, Locale.US);
        String germany = formatter.print(money, Locale.GERMANY);

        System.out.println("amount=" + money.amount().toPlainString());
        System.out.println("currency=" + money.currency().getCurrencyCode());
        System.out.println("us=" + us);
        System.out.println("germany=" + germany);

        DefaultFormattingConversionService conversionService =
                new DefaultFormattingConversionService();
        conversionService.addFormatter(formatter);

        MoneyFormatter.Money fromService = conversionService.convert(
                "2,500.75", MoneyFormatter.Money.class);

        System.out.println(
                "service.amount=" + fromService.amount().toPlainString());

        try {
            formatter.parse("not-a-number", Locale.US);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid=" + ex.getClass().getSimpleName());
        }
    }
}
~~~

The class and nested type are referenced as `MoneyFormatter.Money`. The program uses `Formatter` directly and also registers the same formatter with `DefaultFormattingConversionService` to demonstrate registry-based conversion.

### 6.3. Maven dependencies and running

The project requires JDK 17+ and Maven. Create `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>money-formatting-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Java files required in the same project:

- `src/main/java/example/MoneyFormatter.java`
- `src/main/java/example/MoneyFormattingDemo.java`

Run from the directory containing `pom.xml`:

~~~bash
java -version
mvn -version
mvn -q compile exec:java -Dexec.mainClass=example.MoneyFormattingDemo
~~~

Expected program output (excluding Maven logs):

~~~text
amount=1234.50
currency=EUR
us=€1,234.50
germany=1.234,50 €
service.amount=2500.75
invalid=IllegalArgumentException
~~~

The space before the `€` symbol in the German locale output may be a **non-breaking space**; exact rendering depends on JDK/CLDR. Numeric values, currency codes, and round-trip behavior are what tests should assert; avoid writing tests comparing hardcoded formatted strings across all JDKs if runtime locale data can vary.

## 7. Registering formatters in Spring MVC

Formatters can be registered centrally via `WebMvcConfigurer#addFormatters`:

~~~java
@Configuration
public class WebFormattingConfiguration implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addFormatter(
                new MoneyFormatter(Currency.getInstance("EUR")));
    }
}
~~~

This is a **configuration snippet**, requiring `@Configuration`, `WebMvcConfigurer`, `FormatterRegistry`, and `Currency` imports. The EUR currency here is fixed for the example; in real applications, do not apply EUR to every transaction if users/products have different currencies. You can register formatters by type or field, or provide a resolver/service that determines currency from trusted transaction context.

When Spring MVC receives a DTO with a `MoneyFormatter.Money` property, `WebDataBinder`/`ConversionService` can use the formatter to parse form values and the printer to format the object. Selecting a transaction's currency must follow the endpoint contract, not display clues.

With Spring Boot, add only one appropriate web stack. An MVC project uses the MVC/web starter matching the Boot version; then configure formatters via Spring MVC's mechanism. Do not instantiate a private `DefaultFormattingConversionService` inside a controller expecting it to modify the application-wide registry.

### Field type and field annotations

Beyond type-based configuration, Spring offers annotation formatting such as `@NumberFormat`. Example:

~~~java
public class PriceForm {

    @NumberFormat(style = NumberFormat.Style.CURRENCY)
    private BigDecimal amount;

    // Getters/setters...
}
~~~

This is an **illustrative class snippet**. Import `org.springframework.format.annotation.NumberFormat`—do not confuse it with `java.text.NumberFormat`. Both share the same simple name yet belong to different packages with different purposes.

If you want to register rules driven by a custom annotation, Spring provides `AnnotationFormatterFactory`; the factory returns a `Parser` and `Printer` tailored to the field type and annotation. This is useful when the same Java type needs multiple formatting rules per field.

## 8. Allowed input data: allowlist, range, and precision

Correct formatting does not mean valid data. For example, `"1,000.00"` may parse into `BigDecimal("1000.00")`, but whether a transaction is allowed up to 1000 is another question.

### 8.1. Currency allowlist

Suppose an endpoint only permits `USD`, `EUR`, and `VND`:

~~~java
private static final Set<String> ALLOWED_CURRENCIES =
        Set.of("USD", "EUR", "VND");

static Currency parseAllowedCurrency(String code) {
    if (code == null || !ALLOWED_CURRENCIES.contains(code)) {
        throw new IllegalArgumentException("Currency is not allowed");
    }
    return Currency.getInstance(code);
}
~~~

This is an illustrative snippet requiring `java.util.Set` and `Currency` imports. It verifies **whether the code is in the allowlist**. In production, the list should come from trusted configuration/business knowledge; you may also need to restrict currencies per user, account, product, or country.

Do not accept every valid ISO code in existence if the business does not support it. "Valid by standard" differs from "permitted in this transaction."

### 8.2. Limiting amounts and digits

With Jakarta Bean Validation, you can use:

~~~java
public record PaymentRequest(
        @NotNull
        @DecimalMin(value = "0.01")
        @Digits(integer = 12, fraction = 2)
        BigDecimal amount,

        @NotBlank
        String currency) {
}
~~~

This is an **illustrative record DTO**, requiring `jakarta.validation.constraints.*` imports, a configured provider, and validation activation via `@Valid`/`@Validated` at the appropriate boundary. The constraints in this example allow amounts from 0.01 upward, with at most 12 integer digits and 2 fractional digits. That is the example's policy, not a universal rule for all currencies. For VND or currencies with different fraction digits, define precision to match business requirements.

If refunds/negative adjustment entries are allowed, `@DecimalMin("0.01")` would be wrong for that use case. Design DTOs/constraints per action rather than enforcing a "price must be positive" rule across every workflow.

### 8.3. Validating allowed units

For mass supporting only kg and g:

~~~java
enum MassUnit {
    KG, G
}
~~~

Client-submitted `unit` values must be mapped to an enum or looked up from a configured list. If `LB` or `STONE` is submitted when the app does not support them, reject with a meaningful message. Never store unknown units as raw strings and leave downstream calculations guessing.

Similarly, measured quantities must validate dimensions: disallow mass units on a volume field.

### 8.4. Quantity bounds, step increments, and data domains

Some fields require rules beyond min/max:

- Item quantities may require positive integers (`@Min(1)`).
- Weights may require minimum, maximum, and specific precision.
- Prices may allow two-digit scale; FX fees may allow more digits.
- Percentages may be bounded to `0..100` or another business range.
- Units must belong to an allowlist and match the quantity dimension.
- Dates/times must fall within a meaningful transaction window.

Spring Formatter assists with **parsing/printing**; Jakarta Bean Validation/validators/services enforce these constraints.

## 9. Rounding money: enforce at the right business step

`BigDecimal` supports rounding modes via `RoundingMode`. Example:

~~~java
BigDecimal rounded = amount.setScale(2, RoundingMode.HALF_EVEN);
~~~

This is an illustrative snippet requiring `java.math.RoundingMode`. `HALF_EVEN` is one rounding option, not the universally correct default for every legal entity, tax, or currency. Other policies may require `HALF_UP`, `DOWN`, or no rounding at intermediate storage steps.

Rules:

1. Determine amount precision based on currency and business workflow.
2. Round only at designated business points (e.g., per invoice line, invoice total, or at payment settlement); different points can yield different outcomes.
3. Specify the rounding mode explicitly in code rather than relying on implicit defaults.
4. Test exact midpoints between rounding levels, negative numbers (if permitted), many-digit values, and currencies with different minor units.
5. Never use a formatter to silently round stored data. Printing two decimal places does not mean the underlying amount was properly rounded.

## 10. Testing formatting and input validation

A solid test suite should verify at least four categories:

| Category | Input/Test | Expected Result |
| --- | --- | --- |
| Valid parse | Locale-matching number, amount in range | Object with accurate `BigDecimal`/Currency/unit |
| Different locales | US, Germany, France, or product-supported locales | Parses/prints per convention |
| Invalid parse | Text strings, partially parseable strings, wrong grouping per contract | Rejected, records field error |
| Domain validation | Non-allowlisted currency/unit, out-of-range amount, excess scale | Rejected by validation/business rules |

Examples of logic tests to verify:

- `parse("1,234.50", Locale.US)` yields amount `1234.50`.
- `print(money, Locale.GERMANY)` displays the same amount/currency under German conventions.
- `parse("abc", Locale.US)` is rejected.
- `currency="CAD"` is rejected if CAD is not in the allowlist.
- `unit="LB"` is rejected if the app only supports KG/G.
- Amount `0.001` is rejected if the DTO allows at most 2 fractional digits.

Do not test the formatter solely in isolation; also test the registry, `DataBinder`/controller, and validation pipeline to confirm the formatter runs in the intended scope.

### Note on locale output across JDK versions

Locale data can be updated across JDK/CLDR releases. Non-breaking spaces, symbol positions, and separators may shift. For user interfaces, test against the deployment runtime; for machine-to-machine APIs, prefer canonical strings and explicit currency/unit codes instead of relying on localized display strings.

## 11. Common pitfalls

### Using Double for money

Binary floating-point inaccuracies can cause unexpected addition/subtraction results. Use `BigDecimal` or a dedicated money type with explicit rules.

### Storing only currency symbols

`$` is insufficient to identify a currency. Store codes such as `USD`, `CAD`, or `AUD` per transaction contract.

### Letting Locale determine transaction currency

Locale reflects only display conventions; a user in Germany can still transact in USD. Determine currency from the server/domain and verify against an allowlist.

### Entering locale-formatted numbers but parsing with the server's default locale

`1,234.50` and `1.234,50` have different meanings. Use the request/user's proper locale and test multiple locales.

### Treating @NumberFormat as validation

`@NumberFormat` does not guarantee an amount is within an allowed range, uses a permitted currency, or has a valid unit. Add Bean Validation and domain checks.

### Using a fixed pattern for every currency

Not every currency has two fractional digits. Scale and rounding must follow currency/business rules, not just a display pattern.

### Storing units as free-form strings

Arbitrary strings produce unconvertible units. Use an enum/allowlist or a unit-of-measure library with defined dimensions.

### Having a formatter switch currency/unit based on input symbols

Symbols like `$` or `€` can be ambiguous. Accept currency/unit in separate fields and validate server-side; or define an input contract with explicit codes like `USD 10.00`.

### Rounding inside the printer

A printer may display digits according to a style, yet it should never alter business amounts. Round in the service/domain layer per documented policy.

### Checking format only while forgetting size limits

Extremely long strings or large exponents can consume excessive resources or bypass business logic. Enforce input length, precision, scale, and numeric bounds at appropriate request/domain layers.

## 12. Checklist and self-check questions

**Design checklist:**

1. Store money in an exact type like `BigDecimal` paired with a `Currency` code; never rely on display symbols.
2. Store quantities with an appropriate unit and dimension; explicitly define allowed conversions.
3. Choose `@NumberFormat` for standard numeric fields, or `Formatter<T>` for value objects/specialized currencies/units.
4. Obtain `Locale` from the right context; never treat server locale as transaction policy.
5. Parse the entire input; reject malformed or partially parsed strings.
6. Validate allowlists for currency/unit, range, digits, sign, max length, and authorization.
7. Define rounding mode and rounding timing in the domain/service layer.
8. Test the formatter, `ConversionService`, `DataBinder`/controller, validation, and multiple locales on the real runtime.

**Self-check questions:**

1. Why is `BigDecimal` more suitable for money than `double`?
2. Does `Locale.US` force a transaction to use USD? Why or why not?
3. Does `@NumberFormat(style=CURRENCY)` store a currency code inside the object?
4. Why must a value `10` carry a unit before comparing or adding?
5. If a client submits currency `CAD` while the API only supports USD/EUR, which layer must reject it?
6. When should you use `Formatter<Money>` instead of `@NumberFormat` on `BigDecimal`?
7. Why shouldn't the printer decide monetary rounding rules?
8. For the same amount/currency, why can display strings differ between the US and Germany?

**Remember:** formatting determines **how values are parsed and displayed**, the currency/unit model defines **what the value means**, and allowlists/validation/authorization determine **which data is permitted**. Separating these three responsibilities keeps amounts and measurements accurate across locales.

## Official references

- [Spring Framework Reference — Spring Field Formatting](https://docs.spring.io/spring-framework/reference/core/validation/format.html)
- [Spring Framework Reference — ConversionService](https://docs.spring.io/spring-framework/reference/core/validation/convert.html)
- [Spring Framework Javadoc — NumberFormat](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/format/annotation/NumberFormat.html)
- [Spring Framework Javadoc — CurrencyStyleFormatter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/format/number/CurrencyStyleFormatter.html)
- [Spring Framework Javadoc — NumberStyleFormatter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/format/number/NumberStyleFormatter.html)
- [Java SE — BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html)
- [Java SE — Currency](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Currency.html)
- [Jakarta Bean Validation — Specification](https://jakarta.ee/specifications/bean-validation/)
