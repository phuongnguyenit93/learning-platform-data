# Currency Symbols, Display Names, and Default Fraction Digits in Java

## 1. The Problem: "USD" Is Not Synonymous with "$", and Not Every Currency Has Two Decimal Places

E-commerce, accounting, and international trade applications frequently need to display monetary amounts in a way that matches the reader's language. For example, the same amount in US dollars can be expressed by the code `USD`, the symbol `$` or `US$`, or the name "US Dollar" / "Đô la Mỹ". An amount in Japanese yen is typically displayed without fractional digits; the Kuwaiti dinar, on the other hand, has **three** fraction digits in Java's metadata.

To handle this properly, three pieces of information must be separated:

1. **Currency unit** — identified by an ISO 4217 code such as `USD`, `JPY`, `VND`, `KWD`.
2. **Display language/region** — selected via `Locale`, determining the localized symbol or name.
3. **Default fraction digits** — metadata tied to the currency unit, accessed via `Currency.getDefaultFractionDigits()`.

In Java, `java.util.Currency` describes the **currency unit**, while `java.text.NumberFormat` or `java.text.DecimalFormat` handles **formatting the monetary amount**. You should never infer a currency solely from a `$` sign, nor assume that every monetary amount has `2` digits after the decimal point.

**Lesson objectives:** accurately understand the APIs `getCurrencyCode()`, `getSymbol(Locale)`, `getDisplayName(Locale)`, and `getDefaultFractionDigits()`; understand the role of `Locale`; apply currency metadata when formatting; and distinguish default digit counts from real-world payment rules.

## 2. What Is `Currency`? Is It a Monetary Amount?

A `Currency` object is metadata for **a currency unit**. It does not hold a quantity of money. Two values:

```text
amount = 1234.50
currency = USD
```

together describe a monetary amount. `Currency.getInstance("USD")` creates/retrieves the object for the USD unit, but it does not contain `1234.50` and cannot add amounts or convert exchange rates on its own.

Common currency code examples:

| ISO 4217 Code | Unit | Default fraction digits in Java |
| --- | --- | ---: |
| `USD` | US Dollar | 2 |
| `EUR` | Euro | 2 |
| `JPY` | Japanese Yen | 0 |
| `VND` | Vietnamese Dong | 0 |
| `KWD` | Kuwaiti Dinar | 3 |
| `XXX` | ISO 4217 "no currency" code | -1 |

These values reflect the metadata in the JDK/ISO 4217 at the time the data was shipped; currency data may be updated across JDK releases. `XXX` is a special code, not a currency that can be used for payments.

Key APIs:

| API | Role |
| --- | --- |
| `Currency.getInstance("USD")` | Selects the currency unit by ISO 4217 code |
| `Currency.getInstance(locale)` | Determines the currency of the locale's region/`cu` attribute when sufficient data is present |
| `getCurrencyCode()` | ISO 4217 code, e.g., `"USD"` |
| `getNumericCode()` | ISO 4217 numeric code, e.g., 840 for USD |
| `getNumericCodeAsString()` | ISO 4217 numeric code as a 3-digit string |
| `getSymbol(locale)` | Display symbol appropriate for the locale |
| `getDisplayName(locale)` | Currency name localized according to the locale |
| `getDefaultFractionDigits()` | Default number of fraction digits of the currency unit |

`Currency` is different from `Locale`: a locale can suggest a region's commonly used currency, but a locale does not contain a **monetary amount**. A website with a Vietnamese interface can still quote prices in USD, EUR, JPY, or any other supported unit. Do not automatically switch the currency unit just because the user switches the UI language.

## 3. How Do Currency Codes, Symbols, and Display Names Differ?

### 3.1. `getCurrencyCode()`: A Stable Identifier Code

`Currency.getInstance("USD").getCurrencyCode()` returns `"USD"`. The ISO code is technical data used to describe the **unit** in APIs, databases, reports, and inter-service communication.

The code `USD` does not turn into `VND` when changing the display locale. To convert a value from USD to VND, you need exchange-rate rules and an effective timestamp in the business layer; `Currency` does not perform exchange-rate conversion.

### 3.2. `getSymbol(Locale)`: A Display-Context-Dependent Symbol

`getSymbol(Locale.US)` retrieves the symbol suitable for readers in the US locale. For USD, this is typically `$`. When displaying USD in a Vietnamese context, Java may use `US$` to distinguish it from other currencies that also use a dollar sign.

**Do not treat the symbol as a unique identifier key.** Many different currencies use or share the `$` symbol form; the `¥` symbol likewise requires context to distinguish Japanese yen from other units. Store the currency code alongside the amount in your model, not just a symbol character.

Symbols are determined by the JDK's locale data and localization data providers. Hardcoding `"$"`, `"¥"`, or `"₫"` in general logic removes the ability to display naturally across multiple locales.

### 3.3. `getDisplayName(Locale)`: A Translatable Name

`getDisplayName(Locale.US)` gives the currency name in US English. `getDisplayName(Locale.forLanguageTag("vi-VN"))` attempts to retrieve the name in Vietnamese. For USD, the names can be "US Dollar" and "Đô la Mỹ" in the respective JDK/CLDR data.

This name is suitable for currency selector dropdowns, transaction explanations, or accessibility labels. Some interfaces should show **both the code and the name**:

```text
USD — US Dollar
JPY — Japanese Yen
VND — Vietnamese Dong
```

This is an illustrative representation; the exact string is determined by the localization data. If no localized name is available, the API may fall back to the currency code. When legal wording or an organization's official commercial name is required, use an internally governed and translated catalog rather than assuming all JDK names satisfy that contract.

### 3.4. Overloads Without a Locale

`currency.getSymbol()` and `currency.getDisplayName()` use the appropriate default JVM locale. In multi-user web applications, pass an explicit `Locale`:

```java
currency.getSymbol(viewerLocale);
currency.getDisplayName(viewerLocale);
```

Do not call `Locale.setDefault` per request to switch languages; that is shared JVM state and can affect concurrent requests.

## 4. Java 17+ Example: Inspecting Default Fraction Digits

The first example intentionally uses **currency codes and digit counts**, which are easy to verify without depending on how different JDK versions translate names or symbols.

Create the file `CurrencyFractionDemo.java`:

```java
import java.util.Currency;

public class CurrencyFractionDemo {
    public static void main(String[] args) {
        String[] codes = {"USD", "JPY", "VND", "KWD", "XXX"};

        for (String code : codes) {
            Currency currency = Currency.getInstance(code);
            System.out.println(
                    currency.getCurrencyCode() + " -> "
                    + currency.getDefaultFractionDigits()
            );
        }
    }
}
```

Compile and run with JDK 17+:

```bash
javac -encoding UTF-8 CurrencyFractionDemo.java
java CurrencyFractionDemo
```

Stdout with common currency data in current JDKs:

```text
USD -> 2
JPY -> 0
VND -> 0
KWD -> 3
XXX -> -1
```

Explanation:

- `2` for USD means one dollar unit is typically divided into 100 minor units (*cents*) per standard metadata.
- `0` for JPY and VND means **no fraction digits are displayed by default**. This does not mean an application data type can never hold amounts smaller than one unit; quantization and payment acceptance rules must be decided separately.
- `3` for KWD means three fraction digits per metadata (one dinar can be represented in 1,000 minor units).
- `-1` is a special value: no default fraction digits apply; never pass `-1` to `setMinimumFractionDigits`/`setMaximumFractionDigits` as a normal scale.

This information represents **defaults by currency code**. Cash rounding rules, tax calculations, digit counts in payment protocols, or invoice requirements may differ; a clearly defined business policy should be in place.

## 5. Java Example: One Currency, Multiple Display Representations

Run the program below to observe the difference between code, symbol, and display name. Names and symbols are localized data, so **they may vary across JDK versions, CLDR/COMPAT configurations, and systems**.

```java
import java.util.Currency;
import java.util.Locale;

public class CurrencyDisplayDemo {
    public static void main(String[] args) {
        Currency usd = Currency.getInstance("USD");
        Locale englishUS = Locale.US;
        Locale vietnameseVN = Locale.forLanguageTag("vi-VN");

        System.out.println("Code: " + usd.getCurrencyCode());
        System.out.println("Digits: " + usd.getDefaultFractionDigits());
        System.out.println("US symbol: " + usd.getSymbol(englishUS));
        System.out.println("VN symbol: " + usd.getSymbol(vietnameseVN));
        System.out.println("US name: " + usd.getDisplayName(englishUS));
        System.out.println("VN name: " + usd.getDisplayName(vietnameseVN));
    }
}
```

Save as `CurrencyDisplayDemo.java` and run:

```bash
javac -encoding UTF-8 CurrencyDisplayDemo.java
java CurrencyDisplayDemo
```

A **sample output** on OpenJDK 24 with the tested locale data:

```text
Code: USD
Digits: 2
US symbol: $
VN symbol: US$
US name: US Dollar
VN name: Đô la Mỹ
```

Here `usd` does not change. Only the `Locale` passed to the display methods differs. If your machine returns a different symbol or spelling due to its locale data source, it does not mean the USD currency changed: check `getCurrencyCode()` and your JDK environment.

**Principle:** use the code to **identify**, use the symbol or display name to **present**, and keep them separated in your program architecture.

## 6. `Currency.getInstance(Locale)`: Region Usually Determines the Unit, Not Language

`Currency.getInstance(Locale)` attempts to pick a currency based on the country/region indicated by the locale. Two locales with **different languages but the same US region** still typically select USD:

```java
import java.util.Currency;
import java.util.Locale;

public class CurrencyRegionDemo {
    public static void main(String[] args) {
        Locale americanEnglish = Locale.forLanguageTag("en-US");
        Locale americanJapanese = Locale.forLanguageTag("ja-US");
        Locale japaneseJapan = Locale.forLanguageTag("ja-JP");
        Locale vietnameseVietnam = Locale.forLanguageTag("vi-VN");

        System.out.println(
                Currency.getInstance(americanEnglish).getCurrencyCode());
        System.out.println(
                Currency.getInstance(americanJapanese).getCurrencyCode());
        System.out.println(
                Currency.getInstance(japaneseJapan).getCurrencyCode());
        System.out.println(
                Currency.getInstance(vietnameseVietnam).getCurrencyCode());
    }
}
```

File `CurrencyRegionDemo.java`:

```bash
javac -encoding UTF-8 CurrencyRegionDemo.java
java CurrencyRegionDemo
```

Stdout under current region data:

```text
USD
USD
JPY
VND
```

**Key points to understand correctly:**

1. The `ja` part in `ja-US` specifies **the Japanese language**, yet the `US` region still resolves to USD. The language used to translate labels does not determine a transaction's currency unit.
2. `Currency.getInstance(Locale.forLanguageTag("en"))` lacks region information and typically throws `IllegalArgumentException`; do not guess USD solely from English.
3. Java supports the Unicode locale extension `u-cu` to specify a desired currency inside a `Locale`. For example, `Locale.forLanguageTag("en-US-u-cu-jpy")` can resolve to JPY even though the region is US. Therefore, "based solely on region" is a **default rule with exceptions**, not an absolute law.
4. For certain regions without an appropriate ISO currency, the result can be `null`; applications must handle this. Selecting a currency from a region is not equivalent to choosing the actual currency unit of each payment.

**Do not use `Currency.getInstance(userLocale)` to assign a unit to an existing monetary amount.** If an order has `currencyCode="USD"`, it must keep USD regardless of whether the customer visits from Vietnam or Japan. Switching the locale should only change the display style, unless there is an explicit currency conversion operation with an exchange rate and timestamp.

## 7. Where Are Default Fraction Digits Used?

`getDefaultFractionDigits()` returns the fractional length **commonly** used for the currency unit. It does not indicate the exact monetary value held or forbid amounts with more decimal digits.

Scenarios:

| Need | Role of fraction digits |
| --- | --- |
| Displaying USD prices | Typically choose 2 digits, e.g., `$12.50` |
| Displaying JPY prices | Typically 0 digits, e.g., `¥1250` depending on grouping and locale |
| Displaying KWD | Typically 3 digits |
| Storing business values | Requires scale and `BigDecimal` per contract, not just per formatter |
| Collecting cash | May require rounding to cash increments, differing from fraction digits metadata |
| Sending transactions to a payment gateway | Must follow gateway specifications for minor units, scale, and currency type |

Some currencies have specific **cash rounding increments** (e.g., rounding cash to a given step), which are not fully encoded in the single integer returned by `getDefaultFractionDigits()`. Default digit counts also do not guarantee that **every payment system** accepts that scale. One system may expect integer "minor units," while another uses decimal strings; that is a separate API contract.

For `digits == -1` (such as `XXX`), have an explicit policy instead of assuming `-1` means "no decimal part."

## 8. Formatting Money with `NumberFormat`: Unit and Presentation Are Two Steps

To format a monetary amount, you can create a locale-based formatter:

```java
NumberFormat formatter =
        NumberFormat.getCurrencyInstance(displayLocale);
```

This formatter is typically configured with the locale's default currency, symbol placement, grouping separators, and default fraction digits. `NumberFormat` has a `setCurrency(Currency)` method to change **the currency unit being formatted** without changing the entire display locale.

**Common pitfall:** calling `setCurrency` on a formatter **does not automatically update** the minimum and maximum fraction digits of an existing formatter. For instance, a US formatter typically has 2 digits; if you only switch its currency to JPY, the formatter may still keep 2 digits as before. To display using the new currency's fraction digits, explicitly update min/max digits.

### Java 17+ Example: Changing Currency and Manually Updating Fraction Digits

```java
import java.text.NumberFormat;
import java.util.Currency;
import java.util.Locale;

public class CurrencyFormatterDigitsDemo {
    public static void main(String[] args) {
        NumberFormat format =
                NumberFormat.getCurrencyInstance(Locale.US);

        System.out.println(
                format.getCurrency().getCurrencyCode() + ": "
                + format.getMinimumFractionDigits() + "/"
                + format.getMaximumFractionDigits());

        Currency jpy = Currency.getInstance("JPY");
        format.setCurrency(jpy);

        System.out.println(
                format.getCurrency().getCurrencyCode() + ": "
                + format.getMinimumFractionDigits() + "/"
                + format.getMaximumFractionDigits());

        int digits = jpy.getDefaultFractionDigits();
        if (digits >= 0) {
            format.setMinimumFractionDigits(digits);
            format.setMaximumFractionDigits(digits);
        }

        System.out.println(
                format.getCurrency().getCurrencyCode() + ": "
                + format.getMinimumFractionDigits() + "/"
                + format.getMaximumFractionDigits());
    }
}
```

Save as `CurrencyFormatterDigitsDemo.java` and run:

```bash
javac -encoding UTF-8 CurrencyFormatterDigitsDemo.java
java CurrencyFormatterDigitsDemo
```

Stdout under standard US currency configuration:

```text
USD: 2/2
JPY: 2/2
JPY: 0/0
```

This program shows that **changing the currency** and **changing the display precision** are two separate operations. After calling `setCurrency(jpy)`, the object is indeed configured for JPY, yet min/max fraction digits have not changed. After reading JPY's metadata and resetting min/max, the formatter will display 0 decimal digits.

Do not use `getDefaultFractionDigits()` as a command to **round every calculation**. Apply it only once the corresponding display policy is confirmed.

### A Controlled Formatter Configuration Helper

The code below is an **illustrative helper method** for use inside a Java class that imports `java.text.NumberFormat`, `java.util.Currency`, and `java.util.Locale`. It demonstrates how to avoid applying `-1`:

```java
static NumberFormat currencyFormatter(
        Locale displayLocale, Currency currency) {

    NumberFormat format =
            NumberFormat.getCurrencyInstance(displayLocale);
    format.setCurrency(currency);

    int digits = currency.getDefaultFractionDigits();
    if (digits >= 0) {
        format.setMinimumFractionDigits(digits);
        format.setMaximumFractionDigits(digits);
    }
    return format;
}
```

In a real project, you can add parameters according to product policy to control rounding, format patterns, and special cases. `NumberFormat` is an abstraction: do not force-cast it to `DecimalFormat` unless you are sure which instance the provider returns. When advanced pattern adjustments are needed, check the formatter type and library contract.

## 9. `DecimalFormat`, Grouping Separators, and Symbol Placement

`NumberFormat.getCurrencyInstance(locale)` is usually the right choice if you only need to display money per locale. If fine-grained formatting customization is needed, `DecimalFormat` supports patterns and `DecimalFormatSymbols`:

```java
Locale locale = Locale.US;
NumberFormat base = NumberFormat.getCurrencyInstance(locale);
String formatted = base.format(1234.5);
```

The snippet above is **not a standalone program** and only illustrates the API. With `Locale.US` and USD, common output is `$1,234.50`. In other locales, the symbol may appear before or after the number, and decimal/grouping separators and whitespace may differ.

In `DecimalFormat`, the `¤` symbol in a pattern carries currency semantics: a single `¤` represents the currency symbol, double `¤¤` represents the ISO code; other pattern variants serve other display styles. This is the **currency sign character U+00A4**, not a "per-mille sign," and you should never replace `¤` with a hardcoded `$` for all currencies.

If you always need to show the code, consider a pattern using `¤¤` or a UI layout that explicitly renders the ISO code. When building an internationalized UI, however, prefer the JDK's localized formatting and test with real data rather than manually prepending or appending symbols to strings.

**Note when formatting KWD:** if a US-based formatter initially has 2 digits and is switched to KWD, you must verify that setting min/max fraction digits to 3 is appropriate. Configuring with `setCurrency(KWD)` alone does not guarantee 3-digit fractional formatting.

## 10. Storing Monetary Amounts: Use a Currency Code and Appropriate Numeric Precision

Keep unit and quantity information cleanly separated:

```java
import java.math.BigDecimal;
import java.util.Currency;

public record Money(BigDecimal amount, Currency currency) {
    public Money {
        if (amount == null || currency == null) {
            throw new IllegalArgumentException(
                    "amount and currency are required");
        }
    }
}
```

Save this in `Money.java`. Since `record` is available in Java 17, this snippet is a standalone compilable data type. Usage example in other Java code:

```java
Money price = new Money(
        new BigDecimal("12.50"),
        Currency.getInstance("USD"));
```

The instantiation snippet is **illustrative code inside a method** and not a standalone program. `Money` above does not automatically enforce addition/subtraction, exchange-rate conversion, or rounding rules; those operations must be designed according to business requirements. When storing or transmitting between services, preserve the `USD` currency code alongside the decimal value.

**Never use a symbol to infer a currency code.** A request like `{"amount":"12.50","symbol":"$"}` does not uniquely identify whether it is USD, CAD, AUD, or another unit. API contracts should carry a `currencyCode` field.

For money, `BigDecimal` is generally more appropriate than `double` because many decimal values cannot be represented exactly in binary floating point. When creating a `BigDecimal` from a decimal string, use `new BigDecimal("12.50")` rather than constructing directly from a `double` value if you want to preserve exact decimal representation.

## 11. Some Edge Cases of `Currency`

### 11.1. Unknown Currency

`Currency.getInstance("NOT_A_CODE")` cannot be resolved as a valid unit and throws `IllegalArgumentException`. Calling this API for a currency code is a **code validation** step, not proof that your payment system accepts transactions in that currency.

`Currency.getInstance(Locale)` requires a locale with valid country/region information (unless a valid extension is present). If the locale lacks a region, it may throw `IllegalArgumentException`; for certain regions without a corresponding currency, it may return `null`.

### 11.2. Units with `-1` Fraction Digits

`XXX` and some special codes have no default fraction digits. When `getDefaultFractionDigits() == -1`, you must apply a dedicated policy. Do not pass negative values to fraction-digit setters, and do not infer a valid monetary amount from a special code.

### 11.3. Display Codes vs. ISO Numeric Codes

`getNumericCode()` and `getNumericCodeAsString()` are useful when integrating protocols that use **ISO 4217 numeric codes**. Use the string version if you must preserve exact three-digit formatting for numeric codes with leading zeros. Do not treat numeric codes as monetary amounts or conversion factors.

### 11.4. Currency Data Changes Over Time

Currency units, names, symbols, and region metadata can change with ISO updates and JDK locale providers. Therefore, in legal/financial systems, pin the appropriate JDK/CLDR version, test the currencies actually used, and do not assume name/symbol lists are immutable across environments.

### 11.5. Both `Currency` and `Locale` Have Distinct Roles

Consider an application with a `vi-VN` interface whose price list is in USD: select `Currency.getInstance("USD")` to retain the unit, and select `vi-VN` as the display locale. If the user later switches the UI language to `en-US`, **the quantity and currency unit remain USD**; only the presentation (name/symbol/separators) changes. Converting USD to VND is a separate operation involving exchange rates and business rules.

## 12. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Storing `"$"` instead of `"USD"` | Cannot uniquely identify the currency unit | Store the ISO code |
| Calling `getSymbol()` without a locale in a web app | Depends on JVM/server default | Pass the user's locale |
| Thinking `getDisplayName()` is an ISO code | Value changes by language | Use `getCurrencyCode()` for data |
| Assuming every unit has 2 fraction digits | JPY/VND/KWD get formatted incorrectly | Read metadata and apply explicit policy |
| Calling `setCurrency(JPY)` assuming precision updates too | Formatter may still retain 2 digits | Reset min/max explicitly when appropriate |
| Passing `-1` to fraction digits setters | Invalid scale | Handle special cases explicitly |
| Inferring an amount's unit from `userLocale` | Unintended currency changes | Store currency per transaction |
| Using a symbol as an exchange-rate indicator | Two currencies can share the same symbol | Distinguish ISO codes and use separate exchange rates |
| Using a formatter to normalize stored values | Digit loss due to rounding | Keep original decimals; format only for display |
| Confusing default fraction digits with cash rounding | Incorrect payment settlement rules | Follow API contracts and cash rounding rules |
| Sharing a mutable `NumberFormat` across threads | Race conditions when changing currency/precision | Create instances per request or manage concurrency |
| Treating JDK translated names as mandatory product labels | Names can change across CLDR/providers | Test and maintain a product glossary if required |

`NumberFormat` and `DecimalFormat` are stateful mutable formatters; do not mutate a shared formatter concurrently across multiple requests. `Currency` describes a unit and can be reused, while the **formatting formatter** itself should be created or managed appropriately per locale/currency/configuration.

## 13. Testing Checklist

When implementing, verify the following points:

1. **Metadata:** USD=2, JPY=0, VND=0, KWD=3, XXX=-1 under the target runtime environment.
2. **Identification:** `getCurrencyCode()` stays constant even when changing the display locale.
3. **Names/symbols:** test locales such as `en-US`, `vi-VN`, `ja-JP`; do not hardcode the same symbol across all languages.
4. **Region:** `ja-US` resolves to the US region's currency, while `ja-JP` resolves to JP; test the `u-cu` extension if the application uses it.
5. **Formatter precision:** after `setCurrency`, check min/max fraction digits; do not assume automatic updates.
6. **0- and 3-digit units:** test formatting JPY/VND/KWD with `BigDecimal` and rounding rules.
7. **Invalid codes:** handle `IllegalArgumentException`, `null`, and `-1` fraction digits appropriately.
8. **Business amounts:** store both amount and currency code; never infer currency from symbol or user locale.
9. **Environment:** test on the target JDK version and locale provider; if translated name output changes, classify whether it is a metadata difference or a business bug.
10. **Concurrency:** ensure formatters do not have their configuration mutated across threads sharing an instance.

### Exercises

- Print `getSymbol(Locale.US)`, `getSymbol(Locale.forLanguageTag("vi-VN"))`, and both `getDisplayName` calls for USD and JPY. Note the differences, without turning the results into immutable assumptions across all JDKs.
- Create `NumberFormat.getCurrencyInstance(Locale.US)`, switch it to KWD via `setCurrency`, and update min/max fraction digits using `getDefaultFractionDigits()`. Verify `3/3`.
- Create a `Money` instance holding amount `12.50` and USD; switch the display locale to `vi-VN` without changing `currency.getCurrencyCode()`.
- Explain why `currency.getSymbol(Locale.US).equals("$")` cannot be used as a condition to conclude that every number with a `$` symbol is USD.
- Suppose an API receives `amount=1234.567`, `currencyCode=JPY`. Decide explicitly on the decimal handling rule per business requirements **before** displaying; do not silently round the data just because the formatter defaults to 0 digits.

## 14. Key Takeaways

**ISO 4217 codes** identify currency units; **symbols and display names** are **locale-based presentation** data; **default fraction digits** are metadata indicating the typical number of fractional digits for a unit. These three things serve three distinct purposes.

When formatting a monetary amount, keep **amount + currencyCode** in the data, select the **display locale**, create the appropriate `NumberFormat`, set the currency, and verify precision if the unit changed. When processing payments or exact calculations, apply business contracts and an appropriate decimal type, never equating JDK fraction digits with all cash or gateway rules.

## References

- [Oracle Java 21 — Currency](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Currency.html)
- [Oracle Java 21 — NumberFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/NumberFormat.html)
- [Oracle Java 21 — DecimalFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/DecimalFormat.html)
- [Oracle Java 21 — Locale](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Locale.html)
- [ISO 4217 — Currency Codes](https://www.iso.org/iso-4217-currency-codes.html)