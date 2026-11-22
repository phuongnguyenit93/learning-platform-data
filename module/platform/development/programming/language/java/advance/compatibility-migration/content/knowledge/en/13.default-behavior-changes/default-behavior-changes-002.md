
# Locale, CLDR Data, and Number or Currency Formatting

During a Java upgrade, many compatibility issues do not appear as compile errors, `NoSuchMethodError`, or `UnsupportedClassVersionError`. The application still starts normally, yet financial reports display different separators, currency symbols appear in a new position, numbers are grouped differently, or parsers no longer accept a string saved from an older version. These differences can originate from the **default Locale**, **internationalization data**, **CLDR data sources**, and how Java selects the locale data provider.

This is an issue belonging to the **Default Behavior** group in *Java Advance Compatibility Migration*: source code, bytecode, and public APIs may remain unchanged, yet the behavior observed at runtime changes due to the JDK, locale data, deployment environment, and dependencies.

This lesson explains the relationships among `java.util.Locale`, Unicode CLDR, `NumberFormat`, `DecimalFormat`, `DecimalFormatSymbols`, `Currency`, and what needs to be verified when upgrading the JDK. The focus is on detecting **behavioral changes that impact users and protocols**, rather than trying to memorize a fixed formatted string for every Java version.

## 1. Why Can Changing the JDK Alter Formatting Without Changing Code?

Consider the Java code:

~~~java
import java.math.BigDecimal;
import java.text.NumberFormat;

public class Report {
    public static void main(String[] args) {
        BigDecimal amount = new BigDecimal("1234567.89");
        System.out.println(NumberFormat.getCurrencyInstance().format(amount));
    }
}
~~~

The code does not specify a locale. `NumberFormat.getCurrencyInstance()` therefore depends on the process's **default formatting locale**. The output can differ between a developer machine and the production environment, or across JDK configurations.

Even when the locale is explicitly specified:

~~~java
NumberFormat formatter =
        NumberFormat.getCurrencyInstance(Locale.forLanguageTag("fr-FR"));
~~~

there is still the data factor: how currency symbols are written, grouping rules, decimal separators, whitespace, and formatting patterns supplied by the JDK's locale data provider. This dataset can be updated across JDK releases.

Sources leading to changes include:

- The JVM's default locale differs across environments.
- The JDK changes the order or set of locale data providers.
- The Unicode CLDR version used by the JDK is updated.
- Formatting rules for a locale are revised.
- Defaults for decimal fraction digits or currency symbols are updated.
- Dependencies such as ICU4J or JSON/templating libraries have different versions or configurations.
- Application code relies on `Locale.getDefault()` or `NumberFormat.getInstance()` in unintended places.

**Distinguish three layers:** *business value* (for example, 1234567.89), *presentation rules* (locale, pattern, currency), and *output string* (display text). If these are mixed together, a presentation change can become a data error.

## 2. What Is Locale?

`java.util.Locale` describes the selection of language, region, script, and extensions related to how data is processed culturally/linguistically.

Example:

~~~java
import java.util.Locale;

Locale vietnamese = Locale.forLanguageTag("vi-VN");
Locale german = Locale.forLanguageTag("de-DE");
Locale usEnglish = Locale.forLanguageTag("en-US");

System.out.println(vietnamese.toLanguageTag());
System.out.println(german.getLanguage());
System.out.println(usEnglish.getCountry());
~~~

Common components:

| Component | Example | Meaning |
|---|---|---|
| Language | `vi`, `en`, `de` | Language |
| Region | `VN`, `US`, `DE` | Region or country per corresponding code |
| Script | `Latn`, `Cyrl` | Writing system |
| Variant | Depends on locale | Additional variant |
| Unicode locale extension | `u-nu-latn` | Selects locale processing characteristics supported by the provider |

Do not equate locale with time zone, charset, or currency unit:

- `Locale` is the language/region context for choosing presentation rules.
- `ZoneId` is a time zone identifier.
- `Charset` is a character encoding rule.
- `Currency` is a currency unit code and related metadata.
- `BigDecimal` represents an exact decimal number without containing a locale.

A locale may suggest a default currency, but **financial transactions must store the currency separately**. For example, a customer in Vietnam can still pay in USD.

### 2.1. Default Locale vs. Explicitly Selected Locale

Comparison:

~~~java
NumberFormat a = NumberFormat.getNumberInstance();
NumberFormat b =
        NumberFormat.getNumberInstance(Locale.forLanguageTag("vi-VN"));
~~~

`a` depends on the JVM's default locale; `b` uses the locale explicitly specified by the application. Both can still depend on the data provider and data version in the JDK.

When outputting machine-readable data, using the default locale is usually a design flaw. When displaying to users, the locale must come from the user profile, request, product configuration, or defined business rules.

### 2.2. Default Locale Has Two Important Categories

Java supports default categories:

- `Locale.Category.DISPLAY`: used for display names and UI content.
- `Locale.Category.FORMAT`: used for locale-sensitive formatting operations.

Example:

~~~java
import java.util.Locale;

public final class Defaults {
    public static void main(String[] args) {
        System.out.println(Locale.getDefault());
        System.out.println(
                Locale.getDefault(Locale.Category.DISPLAY));
        System.out.println(
                Locale.getDefault(Locale.Category.FORMAT));
    }
}
~~~

`NumberFormat` typically relies on the default formatting locale when no locale is explicitly passed. Do not assume `DISPLAY` and `FORMAT` are always equal.

Changing the default locale within a JVM via `Locale.setDefault(...)` is a process-wide operation that can affect other threads. In multi-request services, pass the locale explicitly instead of mutating global state per user.

### 2.3. BCP 47 and Locale Selection

`Locale.forLanguageTag("vi-VN")` is suitable when receiving language tags from configuration. The locale code is normalized and does not necessarily share the exact structure of every legacy `language_COUNTRY` string.

Explicit construction example:

~~~java
Locale locale = new Locale.Builder()
        .setLanguage("vi")
        .setRegion("VN")
        .build();
~~~

If accepting a client-supplied locale, define the list of locales supported by the product, fallback rules, and how invalid inputs are handled. Do not accept an arbitrary language tag and assume complete formatting data exists for it.

## 3. What Is CLDR and Why Does It Matter When Upgrading the JDK?

The **Unicode Common Locale Data Repository (CLDR)** is an internationalization dataset describing rules for language names, regions, number formatting, separators, currency symbols, date/time patterns, plural rules, and many other localization details.

Java can use data derived from CLDR to serve APIs such as `NumberFormat`, `DateFormat`, and other localization components.

### 3.1. CLDR Is Not an API Called Directly

With the code:

~~~java
NumberFormat formatter =
        NumberFormat.getNumberInstance(Locale.forLanguageTag("de-DE"));
~~~

the developer calls the Java SE API. The result depends on the runtime's implementation and locale data; there is no “direct call to CLDR” in the code.

This explains why the same API can still return a different string after a JDK upgrade:

- The new JDK carries updated locale data.
- A CLDR rule was changed/corrected.
- The selected provider differs from before.
- Fallback data for a locale missing details is resolved differently.

**There is no general guarantee that output characters for every locale will remain identical across all JDK updates.**

### 3.2. Provider Change Milestones

JDK 9 made CLDR the preferred source of locale data as guided by JEP 252, instead of keeping only the legacy compatibility dataset as default in earlier JDKs. Subsequent releases also introduced changes to available providers and their corresponding data.

Key points to remember during migration:

1. The source and target JDKs may have **different default providers**.
2. Certain provider names/aliases and the COMPAT mechanism belong to a historical phase of the JDK; do not assume they will exist forever in newer Java versions.
3. CLDR data can change even when the provider remains CLDR.
4. Read release notes and migration guides, and verify on the actual JDK rather than inferring from version numbers alone.

### 3.3. The java.locale.providers Property

On JDKs that support it, the locale provider order can be specified via a system property:

~~~bash
java -Djava.locale.providers=CLDR,SPI -jar app.jar
~~~

The example above instructs the JDK's provider mechanism to consult CLDR and then SPI. It **does not make CLDR data immutable** and does not mean every application server/framework follows a single formatting source.

Some older systems use a configuration such as:

~~~text
-Djava.locale.providers=COMPAT,CLDR
~~~

However, `COMPAT` is a historical compatibility dataset and should not be used as a long-term strategy if the target JDK no longer provides or supports that provider. Check the documentation for the specific JDK version before proposing this property.

**Do not treat forcing an old provider as the default migration solution.** Prioritize defining the format contract and updating code/tests to accept published rules.

### 3.4. LocaleServiceProvider and SPI

Java has a Service Provider Interface (`java.util.spi`) mechanism for certain locale services. An application can package its own provider if specialized rules are needed. This creates an additional source of variation beyond JDK data.

When analyzing differences:

- Check whether an SPI implementation is on the classpath/module path.
- Check `META-INF/services` or the corresponding module declaration.
- Check whether the `java.locale.providers` property allows using SPI.
- Check priority order and fallback.
- Check the actual artifact, not just source code.

Do not add a custom SPI to “freeze” every locale when only a protocol format needs stability. A dedicated canonical format is usually simpler and easier to test.

## 4. What Components Make Up Number Formatting Rules?

A number like `1234567.89` can be represented in many ways depending on the locale:

- Thousands/grouping separator.
- Decimal separator.
- Negative sign placement rules.
- Minimum/maximum fraction digits.
- Numeral system/digit set.
- Percent symbol or exponent.
- Special whitespace between the number and unit.
- Patterns for negative numbers, positive numbers, and symbols.

Examples of representation under common conventions (illustrative only, **not guaranteed output of any specific JDK version**):

| Locale or convention | Example string | Notes |
|---|---|---|
| en-US convention | `1,234,567.89` | Comma grouping, dot decimal |
| de-DE convention | `1.234.567,89` | Dot grouping, comma decimal |
| A French-style convention | `1 234 567,89` | Grouping separator may be a narrow Unicode space |
| Canonical machine-readable string | `1234567.89` | Uses dot, no grouping |

Characters that look like spaces can differ at the code point level: `U+0020` (space), `U+00A0` (no-break space), and `U+202F` (narrow no-break space). Changing one of these characters can cause snapshot tests or manual parsers to fail.

### 4.1. NumberFormat.getNumberInstance

~~~java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.util.Locale;

public class NumberExample {
    public static void main(String[] args) {
        BigDecimal value = new BigDecimal("1234567.89");
        Locale[] locales = {
                Locale.forLanguageTag("en-US"),
                Locale.forLanguageTag("de-DE"),
                Locale.forLanguageTag("vi-VN")
        };

        for (Locale locale : locales) {
            NumberFormat formatter =
                    NumberFormat.getNumberInstance(locale);
            System.out.println(
                    locale.toLanguageTag() + ": " +
                    formatter.format(value));
        }
    }
}
~~~

Run the same class file on both JDKs to record outputs. Do not hardcode expected strings from documentation examples if the application must support multiple providers/JDKs; instead, maintain a clear test plan for contracts requiring stability.

### 4.2. DecimalFormatSymbols

`DecimalFormatSymbols` helps inspect symbols per locale:

~~~java
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class SymbolsExample {
    static String codePoint(char value) {
        return String.format("U+%04X", (int) value);
    }

    public static void main(String[] args) {
        Locale locale = Locale.forLanguageTag("fr-FR");
        DecimalFormatSymbols symbols =
                DecimalFormatSymbols.getInstance(locale);

        System.out.println(
                "decimal=" + codePoint(symbols.getDecimalSeparator()));
        System.out.println(
                "grouping=" + codePoint(symbols.getGroupingSeparator()));
        System.out.println(
                "currency=" + symbols.getCurrencySymbol());
    }
}
~~~

Printing code points helps distinguish visually similar characters. If you need exact comparison of Unicode strings containing supplementary characters, iterate using `String.codePoints()`; the example above uses `char` because those specific getters return `char` values.

### 4.3. Patterns Do Not Completely Replace Locale

With `DecimalFormat`, the pattern determines the formatting structure, but the symbols in the result can still come from the locale's `DecimalFormatSymbols`.

~~~java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class PatternExample {
    public static void main(String[] args) {
        Locale locale = Locale.forLanguageTag("de-DE");
        DecimalFormatSymbols symbols =
                DecimalFormatSymbols.getInstance(locale);

        DecimalFormat format =
                new DecimalFormat("#,##0.00", symbols);

        System.out.println(
                format.format(new BigDecimal("1234567.8")));
    }
}
~~~

In a non-localized pattern, commas and periods act as pattern syntax; when formatted, the actual symbols depend on `symbols`. If the application needs a fixed machine-readable string, do not allow different locales to alter how the data is emitted.

## 5. Currency Formatting: Two Independent Decisions

Currency requires both a **numeric value** and a **currency unit**. Locale primarily determines presentation, whereas the transaction determines the currency.

~~~java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.util.Currency;
import java.util.Locale;

public class CurrencyExample {
    public static void main(String[] args) {
        BigDecimal amount = new BigDecimal("1234567.89");
        Locale viewerLocale = Locale.forLanguageTag("vi-VN");
        Currency transactionCurrency =
                Currency.getInstance("USD");

        NumberFormat formatter =
                NumberFormat.getCurrencyInstance(viewerLocale);
        formatter.setCurrency(transactionCurrency);

        System.out.println(formatter.format(amount));
    }
}
~~~

In the example, the user has a Vietnamese-Vietnam locale, but the transaction is denominated in USD. `setCurrency` selects the currency unit to render; the resulting string, symbol, and other formatting rules may depend on the locale/provider and formatter configuration. Never infer a transaction's currency solely from the viewer's locale.

### 5.1. Locale Is Not a Currency Code

| Value | Example | Purpose |
|---|---|---|
| Locale | `vi-VN` | Selects presentation rules |
| Currency code | `VND`, `USD`, `EUR` | Identifies the currency unit |
| Amount | `new BigDecimal("125000.50")` | Exact numeric value |
| Currency symbol | `₫`, `$`, `€` | Display symbol, which may vary by locale |
| Formatted text | For example, a locale-formatted string | For human readers, not machine identification |

A symbol like `$` can represent multiple currencies. Therefore, **ISO 4217 codes** are generally a safer identifier choice than symbols in interchange data. If the product uses assets or units outside ISO 4217, design custom codes with a clear contract.

### 5.2. Currency Decimal Fraction Digits

`Currency.getDefaultFractionDigits()` provides the default number of decimal fraction digits for the currency unit, based on data available in the runtime. Not every currency has two fraction digits.

~~~java
import java.util.Currency;

public class Digits {
    public static void main(String[] args) {
        for (String code : new String[] {"USD", "VND", "JPY"}) {
            Currency currency = Currency.getInstance(code);
            System.out.println(
                    code + " -> " +
                    currency.getDefaultFractionDigits());
        }
    }
}
~~~

For certain special units, the value can be `-1` when fraction digits do not apply. When designing monetary data, define the product's precision, rounding, and legal/business rules; default fraction digits metadata does not itself replace business rules.

A common mistake is treating the formatter like a calculator and letting it round transaction amounts automatically. `NumberFormat` only renders strings; calculated values must be processed beforehand according to explicit policy.

### 5.3. Symbol Placement and Whitespace

A locale may place the currency symbol before or after the number, with or without spacing; sometimes using a narrow symbol, three-letter currency code, or non-breaking space. These details can change with CLDR data.

**Do not parse currency by stripping a fixed symbol and replacing separators manually.** That approach breaks when the symbol appears in a different position, Unicode whitespace differs, or a symbol is ambiguous across currencies.

### 5.4. setCurrency Is Not Equivalent to Specifying All Numeric Rules

Setting a currency on `NumberFormat` is not a guarantee that the formatter will automatically enforce every business precision requirement. If a specific number of fraction digits is needed, configure it explicitly and test:

~~~java
NumberFormat formatter =
        NumberFormat.getCurrencyInstance(
                Locale.forLanguageTag("en-US"));

formatter.setCurrency(Currency.getInstance("USD"));
formatter.setMinimumFractionDigits(2);
formatter.setMaximumFractionDigits(2);
~~~

Setting fraction digit limits only controls **output formatting**. In accounting calculations, `BigDecimal.setScale(...)` with an appropriate `RoundingMode` must be decided according to business rules before rendering.

## 6. BigDecimal, double, and Rounding When Handling Money

### 6.1. Do Not Construct Exact Monetary Values from Arbitrary double Literals

Example:

~~~java
import java.math.BigDecimal;

BigDecimal risky = new BigDecimal(0.1);
BigDecimal exact = new BigDecimal("0.1");
~~~

`new BigDecimal(0.1)` receives the exact binary value of the `double`, not the exact decimal “0.1” entered by a user. In financial calculations, prefer creating `BigDecimal` from canonical decimal strings or validated input data.

### 6.2. Rounding Is a Business Decision, Not a Locale Concern

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal raw = new BigDecimal("19.995");
BigDecimal displayAmount =
        raw.setScale(2, RoundingMode.HALF_EVEN);
~~~

`RoundingMode.HALF_EVEN` is only an illustrative choice. Domains such as taxes, invoicing, payments, or foreign exchange may require different rules, different rounding points, or line-item rounding instead of total rounding.

You need to define:

- Internal precision.
- Scale at storage time.
- Scale during calculation.
- Rounding rules at each step.
- Display scale per currency unit and product policy.
- Exchange rate source and rate precision if currency conversion is involved.

Do not let CLDR changes accidentally alter summation algorithms or payment outcomes. Locale should only affect presentation unless the business contract states otherwise.

### 6.3. DecimalFormat Is Not Guaranteed Thread-Safe

`NumberFormat` and `DecimalFormat` are stateful formatters and in general are **not safe for concurrent use without synchronization**. Do not share a single mutable instance application-wide and mutate its currency, locale, or fraction digits per request.

For example, create a separate formatter per request or appropriate scope:

~~~java
static String formatMoney(
        BigDecimal amount, Currency currency, Locale locale) {
    NumberFormat formatter =
            NumberFormat.getCurrencyInstance(locale);
    formatter.setCurrency(currency);
    return formatter.format(amount);
}
~~~

If caching formatters is necessary, use a thread-safety strategy and prevent one request's state from leaking into another.

## 7. Locale-Sensitive Number Parsing: A Silent Source of Bugs

When reading user-entered input, `NumberFormat.parse` may interpret periods and commas differently by locale. For example, `"1.234"` can mean one thousand two hundred thirty-four or one point two three four depending on convention.

~~~java
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;

public class ParseExample {
    public static void main(String[] args) {
        String input = "1.234";
        Locale locale = Locale.forLanguageTag("de-DE");

        NumberFormat parser =
                NumberFormat.getNumberInstance(locale);

        ParsePosition pos = new ParsePosition(0);
        Number parsed = parser.parse(input, pos);

        boolean consumedAll =
                parsed != null && pos.getIndex() == input.length();

        System.out.println("parsed=" + parsed);
        System.out.println("consumedAll=" + consumedAll);
    }
}
~~~

### 7.1. Must Verify the Entire Input Was Parsed

Some parsing APIs may read only a valid prefix and stop before the rest. Checking only that the result is non-`null` can still allow strings with trailing characters to be accepted.

Use `ParsePosition` to verify:

- The parser returned a value.
- There is no parse error at the reported position.
- `pos.getIndex() == input.length()` if the contract requires the entire string to be valid.

This only validates locale-specific syntax; you still need to validate value ranges, negative signs, digit counts, and business policies.

### 7.2. Parsing to BigDecimal When Precision Is Required

If the actual formatter is a `DecimalFormat`, you can configure:

~~~java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.util.Locale;

NumberFormat numberFormat =
        NumberFormat.getNumberInstance(
                Locale.forLanguageTag("de-DE"));

if (numberFormat instanceof DecimalFormat decimalFormat) {
    decimalFormat.setParseBigDecimal(true);
    Number value = decimalFormat.parse("1234,56");
    BigDecimal exact = (BigDecimal) value;
    System.out.println(exact.toPlainString());
}
~~~

Check the type before casting, as well as the input and parse position. `setParseBigDecimal(true)` applies to `DecimalFormat`, not a guarantee that every subclass of `NumberFormat` supports this option.

### 7.3. Do Not Reverse-Parse Display Strings as Machine Protocols

A currency string rendered for users may contain:

- Locale-specific currency symbols.
- Non-breaking whitespace.
- Bidi characters in certain languages.
- Different grouping separators.
- Rounding that drops digits compared to the original value.
- Negative signs in different positions.

Do not use it to persist ledgers, pass between services, or recalculate values. Transmit **normalized amount + currency code** in a schema-defined format.

## 8. Protocol Format and UI Format Must Be Separated

### 8.1. Canonical Form for Machine Readability

A system might choose JSON:

~~~json
{
  "amount": "1234567.89",
  "currency": "USD"
}
~~~

The `amount` value is transmitted as a decimal string per contract; `currency` is a separate code. Other cases may use integer minor units if all parties agree on the scale. There is no single representation right for every system; what is essential is **defining and versioning the contract**.

When serializing a `BigDecimal` as a JSON number, verify whether the library and consumers preserve precision. JavaScript and other systems may use floating point for JSON numbers. Decimal strings or integer minor units can be easier to preserve if the contract is properly designed.

### 8.2. `Locale.ROOT` Does Not Solve Everything Automatically

`Locale.ROOT` can be useful for operations independent of any specific language/region:

~~~java
String normalized = "status".toUpperCase(Locale.ROOT);
~~~

However, do not infer that `NumberFormat.getCurrencyInstance(Locale.ROOT)` is the way to produce canonical monetary data. The root locale does not inherently supply transaction currency, precision, or schema. For machine-readable data, use clearly specified APIs and formats—such as `BigDecimal.toPlainString()` for decimal strings—rather than picking an arbitrary locale to obtain a “standard-looking” string.

### 8.3. CSV, Excel, Logs, and Reports

For CSV, clearly decide whether the data serves human readers or machines:

- Machine CSV: canonical numbers, no grouping, separate currency column, standard CSV escaping.
- Human CSV: can be formatted by locale, but you must know which parser will open the file.
- Excel: numbers should be in numeric cells if the workflow permits, with dedicated number formats; do not convert all numbers into text containing currency symbols.
- Logs: prefer structured data or canonical numbers for easy querying; logging/observability UIs can reformat by locale on display.
- PDF/reports: require the recipient's locale and checking fonts/Unicode if currency symbols or special whitespace are used.

Do not let the server's default locale implicitly dictate the format of files exchanged between systems.

## 9. Unicode in Output: A Subtle Visual Change

Formatted output can differ at the code point level while looking nearly identical:

- `U+0020`: SPACE.
- `U+00A0`: NO-BREAK SPACE.
- `U+202F`: NARROW NO-BREAK SPACE.
- `U+200E`: LEFT-TO-RIGHT MARK.
- `U+200F`: RIGHT-TO-LEFT MARK.

A snapshot test doing exact text comparison can fail just because of a non-breaking space. Conversely, a consumer performing `trim()` or manually replacing spaces may miss Unicode characters with different meanings.

### 9.1. Code Point Printing Utility for Diagnostics

~~~java
public class UnicodeInspector {
    public static String describe(String input) {
        StringBuilder result = new StringBuilder();

        input.codePoints().forEach(cp -> {
            if (result.length() > 0) {
                result.append(' ');
            }
            result.append(String.format("U+%04X", cp));
        });

        return result.toString();
    }

    public static void main(String[] args) {
        String value = "\u00A0\u202F";
        System.out.println(describe(value));
    }
}
~~~

When comparing Java 17 with Java 21 or another version, you can store both the rendered string and its sequence of code points. The goal is to understand **where the difference is** before fixing tests or code.

### 9.2. Do Not Blindly Replace All Whitespace

Some Unicode whitespace serves to prevent line breaks between a number and a unit. Replacing them with regular spaces can degrade layout or localization semantics.

If the output is a machine format, redesign serialization rather than arbitrarily normalizing display strings. If the output is UI, preserve the rules of the supported locale unless there is a specific product design requirement.

## 10. Sources of Default Locale in Practice

The result of `Locale.getDefault()` can depend on the operating system, environment settings, JVM properties, and how the application initializes locales. A container may have a different locale from a developer machine.

Items to record when investigating:

- JDK vendor, version, and build.
- OS and container image.
- `Locale.getDefault()`.
- `Locale.getDefault(Locale.Category.FORMAT)`.
- `Locale.getDefault(Locale.Category.DISPLAY)`.
- Language/region-related JVM properties when configured.
- `java.locale.providers` and actual SPI providers.
- Versions of formatting/serialization dependencies.
- Value, pattern, currency code, and rounding policy.

### 10.1. JVM Flags to Set the Default Locale

On JVMs supporting the corresponding system properties, you can configure them at startup:

~~~bash
java -Duser.language=vi -Duser.country=VN -jar app.jar
~~~

However, the default locale is a **process-wide configuration**. If the application serves users across multiple regions, pass the locale per request instead of relying on a single server setting.

If code actively calls `Locale.setDefault` after startup, observed values can also change; pay attention to initialization order and impact scope.

### 10.2. Locale Data in Minimal Containers

Minimal container images may lack expected operating system resources or region settings. However, Java locale data can come from the JDK, not necessarily from all OS locale packages.

Therefore, do not conclude that installing an OS locale package alone will eliminate all Java formatting differences. Check the actual provider, JDK build, and running formatting code.

## 11. Migration Process When Upgrading the JDK

It can be rolled out step by step to avoid behavioral changes without evidence.

~~~mermaid
flowchart TD
    A["Record old JDK and locale config"] --> B["Collect representative outputs"]
    B --> C["Run same artifact/tests on target JDK"]
    C --> D{"Does the difference affect contracts?"}
    D -->|No| E["Update snapshots/evidence under control"]
    D -->|Yes| F["Classify as UI, data, API, or parser"]
    F --> G["Choose explicit locale or canonical format"]
    G --> H["Run regression and consumer tests"]
    E --> H
    H --> I["Record decision and monitor rollout"]
~~~

### Step 1: Survey Format/Parse Sites

Search for APIs and data flows:

~~~bash
rg -n "NumberFormat|DecimalFormat|DecimalFormatSymbols|Currency" src
rg -n "Locale.getDefault|Locale.setDefault|forLanguageTag" src
rg -n "String.format|Formatter|printf|parseBigDecimal" src
rg -n "toString\\(|parse\\(|setCurrency|setRoundingMode" src
~~~

The commands are only examples for a learner's repository; adjust paths and combine with manual analysis. Beyond application source code, inspect code in template engines, report generators, UIs, and serialization frameworks.

### Step 2: Tabulate Dependency Sites

| Usage site | Output type | Current locale | Risk | Contract |
|---|---|---|---|---|
| Order details page | UI | Per user | Low-medium | Localized formatting |
| Partner exchange CSV | Machine-readable | JVM default | High | Canonical decimal and currency code |
| PDF invoice | Document | Per market | High | Business rules, money, and layout |
| User number import | Parser | Per user | High | Accept valid inputs only |
| Transaction logs | Observability | JVM default | Medium | Structured values, stable parsing |
| Test snapshots | Test | Implicit locale | Medium | Must separate formatting from business behavior |

### Step 3: Record Baseline on the Old JDK

For each representative case, record:

- Input data, including negative values, large numbers, small numbers, zero, and boundary rounding values.
- Locale, currency code, and pattern.
- Output string and code points.
- Parse result and parse position if applicable.
- JDK version, provider, and locale-related properties.
- Libraries and formatting configs outside Java SE.

Do not pick only a single value like `1234.56`. Include tests for negative numbers, grouping, currencies not using two decimal digits, percentages, and Unicode characters.

### Step 4: Run the Same Tests on the Target JDK

Run the same tests/harness and the same dependency versions when isolating the JDK change. Only afterward combine dependency upgrades; if everything is upgraded at once, it is hard to tell whether differences come from CLDR/JDK or frameworks.

**Do not round or normalize outputs before comparing** if the goal is to detect differences. Classify the root cause first, then decide whether the contract should be preserved or updated.

### Step 5: Choose a Handling Strategy

There are three main situations:

1. **UI wants to follow the new locale:** update snapshots appropriately after confirming the product accepts the new rules.
2. **Machine data changed:** switch to a canonical format with separate numbers and currency codes; test existing consumers.
3. **Business requires a fixed display string:** publish a dedicated pattern/format, configure it explicitly, and maintain tests against that contract.

Do not pin every system to a historical provider just to keep old snapshots passing; that approach may not be supported on the target JDK and masks a design dependent on the default locale.

### Step 6: Verify on the Deployment Artifact and Environment

Build following the product pipeline, then verify the final artifact on the target JDK in the corresponding container/OS. For a service, test with production locale settings and requests carrying different locales. For reports, inspect both byte-level output and visual presentation.

### Step 7: Deploy and Monitor

Define explicit rollback criteria:

- Import/parse failure rate.
- Invalid transaction values.
- Schema/CSV/API contract discrepancies.
- Display errors affecting invoices or compliance.
- Regressions on clients/consumers.

Do not roll back merely for an approved UI whitespace difference, yet never ignore changes that lose precision or cause parsers to misinterpret monetary amounts.

## 12. Writing Valuable Tests Instead of Brittle Tests

### 12.1. Testing Numeric Logic Independently of Locale

Business logic:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class PriceCalculator {
    public static BigDecimal calculateTax(BigDecimal net) {
        return net.multiply(new BigDecimal("0.10"))
                .setScale(2, RoundingMode.HALF_UP);
    }
}
~~~

Tests should compare numeric values based on business policy, not formatted strings from the default locale.

### 12.2. Testing Formatting with an Explicit Locale

~~~java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.util.Currency;
import java.util.Locale;

public final class MoneyView {
    public static String render(
            BigDecimal amount, String code, Locale locale) {
        NumberFormat format =
                NumberFormat.getCurrencyInstance(locale);
        format.setCurrency(Currency.getInstance(code));
        return format.format(amount);
    }
}
~~~

Formatting tests must specify:

- Locale.
- Currency.
- Input and rounding policy.
- JDK/provider applied for golden output.
- Policy on whether CLDR changes are allowed or disallowed.

If the product requires exact characters (such as invoice print files), golden output tests are useful but must be tied to a runtime version and have a review process when CLDR changes.

### 12.3. Property-Based and Round-Trip Tests

Properties that can be tested:

- Formatting does not crash on valid numbers within the product domain.
- The parser accepts only valid inputs and consumes the entire string.
- When formatting and then parsing back under a **fixed locale and configuration**, values are compared at the precision retained by the format, without expecting to recover rounded-off digits.
- A canonical amount/currency does not change when the UI locale changes.
- Business results do not depend on thread or machine locale settings.

Do not use round-trip as an absolute guarantee for currency formatters with rounding: if output is limited to two decimal digits, parsing cannot recover dropped digits.

### 12.4. Running a JDK/Locale Matrix

Example matrix:

| Runtime | Locale | Currency | Goal |
|---|---|---|---|
| Minimum JDK | en-US | USD | Baseline |
| Target JDK | en-US | USD | Detect default changes |
| Target JDK | vi-VN | VND | Vietnam market display |
| Target JDK | de-DE | EUR | Verify decimal comma/grouping |
| Target JDK | fr-FR | EUR | Verify Unicode whitespace |
| Target JDK | en-US | JPY | Verify currency fraction digits |

These locales/currencies are examples only; the test suite must select according to actual markets and contracts. For the target JDK, also verify across committed supported updates/vendors if exact outputs depend on provider data.

## 13. Common Mistakes

### 13.1. Omitting Locale When Printing Reports

~~~java
String text = NumberFormat.getInstance().format(amount);
~~~

If the report needs `de-DE` formatting while the server defaults to `en-US`, the output will not match expectations. The solution is to pass the product-determined `Locale`, rather than mutating the global default per request.

### 13.2. Assuming a Period Is Always the Decimal Separator

A string `1.234` can have different meanings. Determine the input's locale; for machine-readable APIs, use a canonical format.

### 13.3. Storing Grouped Strings Instead of Numbers

Storing `"1,234.56"` and then parsing it with another locale causes errors or wrong values. Store canonical numeric/decimal values and currency codes; format only at display time.

### 13.4. Using double for Monetary Calculations

`double` is convenient for many numerical problems, but decimal-exact financial calculations generally require `BigDecimal` or minor units with an explicit policy.

### 13.5. Using Currency Symbols as IDs

Currency symbols are not unique and can vary by locale. Use currency codes as identifiers in protocols and databases.

### 13.6. Fixing Snapshots by Stripping All Whitespace

This hides Unicode differences that may be meaningful to the UI and fails to address the data-source issue. Distinguish visual formatting from canonical serialization.

### 13.7. Sharing One NumberFormat Instance Across All Threads

`NumberFormat` and `DecimalFormat` hold mutable state; reusing them without concurrency control can produce corrupted results or mix configurations across requests.

### 13.8. Assuming Locale Only Affects Separators

Locale can also affect numeral systems, ordering, negative signs, currency patterns, and other rules. A manual dot/comma replacement patch is not equivalent to locale-aware formatting.

### 13.9. Forcing an Old Provider Without Checking the Target JDK

The `java.locale.providers` setting is a runtime dependency. Some old providers do not exist in the target JDK; even the CLDR provider updates its data across versions.

### 13.10. Using Locale.ROOT for Transactional Monetary Data

The root locale does not define business currency or precision. Transactional data needs a currency code, an exact amount, and a clear schema.

### 13.11. Testing Only One Locale on a Developer Machine

A bug involving grouping, non-breaking spaces, or negative signs may appear only for certain locales. Test a realistic matrix, including production runtimes and containers.

## 14. Combined Migration Scenario

Suppose an invoicing service initially runs on an older JDK and exports CSV using:

~~~java
String row = orderId + "," +
        NumberFormat.getCurrencyInstance().format(total);
~~~

Upon upgrading the JDK or changing the container image:

- The default locale changes.
- Currency output contains a comma, breaking the CSV structure because it was not escaped.
- The currency symbol appears before/after the number differently than before.
- Numbers are grouped with a Unicode space that differs from a regular space.
- Partners parsing prices from text can no longer read them.
- Unit tests for total calculation logic still pass.

The core problem is not that CLDR is “wrong”; the application used a **presentation format as protocol data**.

A better design:

~~~java
import java.math.BigDecimal;

public record InvoiceAmount(
        BigDecimal amount,
        String currencyCode) {
}
~~~

Export CSV with separate columns and canonical conventions:

~~~text
invoice_id,amount,currency
INV-001,1234567.89,USD
~~~

When displaying the invoice to users, use an explicit locale:

~~~java
Locale locale = Locale.forLanguageTag("vi-VN");
NumberFormat view = NumberFormat.getCurrencyInstance(locale);
view.setCurrency(Currency.getInstance("USD"));
String displayAmount =
        view.format(new BigDecimal("1234567.89"));
~~~

This design separates:

1. **Value** `1234567.89`.
2. **Unit** `USD`.
3. **UI presentation** depending on `vi-VN` and the JDK/provider.

Test the CSV with partner consumers and test the UI with the target locale/JDK. If the CSV must support complex characters in other columns, use a standard CSV writer to handle escaping/quoting; the example above only illustrates three simple columns.

## 15. Strategy Selection Guide by Goal

| Goal | Recommendation |
|---|---|
| Multilingual UI | Pass locale per user/request; use NumberFormat |
| Market-specific invoices or documents | Explicit locale, explicit currency, business rounding, golden tests |
| Database data | Numeric decimal/minor units and separate currency code |
| JSON API | Schema-defined canonical decimal + currency code; avoid presentation formatting |
| Integration CSV | No grouping, consistent decimal separator; proper CSV escaping |
| User input parser | Locale-specific NumberFormat, check full-string consumption and validation |
| Financial calculation | BigDecimal and clear rounding policy |
| Logs/observability | Structured fields or canonical numeric values |
| Regression across JDKs | Compare outputs + code points + provider/JDK metadata |
| Handling CLDR changes | Classify the contract, fix design/tests, or approve new output |
| UI results “identical across all JDKs” | Self-manage rules/data versions where needed; do not assume runtime guarantees |

## 16. Checklist Before Declaring Compatibility

### Locale and Environment

- [ ] Recorded JDK vendor, version, locale provider, and container/OS.
- [ ] Recorded `Locale.getDefault()` and both `DISPLAY` and `FORMAT` categories.
- [ ] Checked the `java.locale.providers` property if used by the system.
- [ ] Confirmed locale comes from the request/user or business configuration.
- [ ] Distinguished locale from timezone, charset, and currency.

### Number Formatting

- [ ] Verified grouping separator and decimal separator on target locales.
- [ ] Checked Unicode whitespace via code points when outputs differ.
- [ ] Tested negative numbers, zero, large/small values, and rounding.
- [ ] Checked `DecimalFormatSymbols` and custom patterns if used.
- [ ] Separated UI formatting from machine-readable formats.

### Currency

- [ ] Exact amount is separated from currency code.
- [ ] Currency symbols are not stored as the sole identifier.
- [ ] Business precision and rounding policies have been defined.
- [ ] Money is not computed by reverse-parsing formatted currency strings.
- [ ] Verified currency fraction digits and appropriate exceptions.
- [ ] Tested currency output across supported markets.

### Migration and Testing

- [ ] Captured baseline outputs on the source JDK.
- [ ] Ran the same cases on the target JDK and recorded code points.
- [ ] Distinguished CLDR/provider changes from dependency changes.
- [ ] Verified parsers consume entire input and reject invalid data.
- [ ] Ran integration tests for CSV, JSON, DB, reports, and clients.
- [ ] Verified thread safety of formatters.
- [ ] Documented which golden strings must remain stable and why.
- [ ] Prepared rollout/rollback plans if changes affect transactions.

## Conclusion

`Locale` determines the formatting context; **CLDR** provides internationalization data; `NumberFormat` and `DecimalFormat` turn numbers into locale-appropriate strings; `Currency` identifies the currency unit and carries related metadata. When upgrading the JDK, these components can produce different results even though source code and bytecode have not changed. That is a form of **behavioral compatibility risk**.

To upgrade safely, pass explicit locales and currencies for display features, store amounts in exact types like `BigDecimal`, separate machine-readable data from presentation strings, and test on the actual JDK/provider. For outputs that must remain invariant, define the format as a separate versioned contract with golden tests; do not expect the default locale or CLDR data across all JDKs to remain unchanged forever.
