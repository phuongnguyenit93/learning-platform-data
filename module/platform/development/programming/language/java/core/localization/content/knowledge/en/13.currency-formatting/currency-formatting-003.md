# NumberFormat.getCurrencyInstance and setCurrency

In Java, `NumberFormat.getCurrencyInstance(...)` creates a monetary amount formatter according to **the display conventions of a locale**; `setCurrency(...)` lets you attach a **specific currency** to that formatter. These two pieces of information are related, yet **not identical**:

- **`Locale`** answers: which display style does the reader expect (currency symbol position, decimal separator, grouping separator, digits, and certain formatting rules)?
- **`Currency`** answers: in **which currency** is the value denominated, such as `USD`, `EUR`, `JPY`, or `VND`?
- **Numeric value** answers: what is the monetary amount before rounding for presentation?
- **Business rules** answer: is currency conversion needed, should rounding happen at the calculation step, or is a custom number of fraction digits required?

For example, a customer using a US English interface may pay **100 EUR**, while a customer in Germany may view an amount of **100 USD**. Therefore, you should not assume that the default currency inferred from a locale is always the actual currency of the transaction.

This lesson explains how to create a currency formatter, change the currency with `setCurrency`, manage fraction digits, symbols, and rounding, and avoid confusing **currency formatting** with **currency conversion**. Examples use Java 17+.

## 1. Related objects and their roles

| API | Role | Notes |
| --- | --- | --- |
| `java.text.NumberFormat` | Abstract type for formatting/parsing numbers | Has locale-based factory methods |
| `NumberFormat.getCurrencyInstance(locale)` | Creates a currency formatter for a locale | Usually carries the locale's default currency |
| `NumberFormat.getCurrencyInstance()` | Creates a currency formatter using the default locale of category `FORMAT` | Unsuitable when a separate locale per user is needed |
| `NumberFormat.setCurrency(currency)` | Changes the currency attached to the formatter | **Does not automatically update min/max fraction digits** |
| `NumberFormat.getCurrency()` | Reads the currently attached currency | Not an exchange-rate conversion API |
| `java.util.Currency` | Represents a currency by ISO 4217 code | For example `Currency.getInstance("EUR")` |
| `Currency.getDefaultFractionDigits()` | Commonly used number of fractional digits for the currency | Can return `-1` when not applicable |
| `java.text.DecimalFormat` | Common implementation allowing detailed patterns | Mutable, not guaranteed to be thread-safe |
| `java.text.DecimalFormatSymbols` | Set of display symbols by locale | Currency symbols and separators can vary by environment |

You can think of `getCurrencyInstance` as **the factory that selects the initial display configuration**, while `setCurrency` is **an operation that modifies part of the configuration on an already created formatter**.

## 2. Creating a currency formatter by locale

Two overloads:

~~~java
NumberFormat byDefault = NumberFormat.getCurrencyInstance();
NumberFormat byLocale =
        NumberFormat.getCurrencyInstance(Locale.US);
~~~

This is an **in-method snippet**, with imports `java.text.NumberFormat` and `java.util.Locale`.

- The **no-argument overload** depends on the default locale for formatting at the time of the call. On different machines or on a server whose default changes, the output can differ.
- The overload **accepting a `Locale`** lets you specify the presentation conventions explicitly. For example, `Locale.US` typically has the default currency `USD` and uses the `$` sign, decimal point `.`, and grouping comma `,`.
- The created formatter is configured with currency, fraction digits, negative sign, and locale/provider-dependent symbols.

Create the file **`CurrencyInstanceDemo.java`**:

~~~java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.util.Locale;

public class CurrencyInstanceDemo {
    public static void main(String[] args) {
        NumberFormat us = NumberFormat.getCurrencyInstance(Locale.US);

        System.out.println(us.getCurrency().getCurrencyCode());
        System.out.println(us.getMinimumFractionDigits());
        System.out.println(us.getMaximumFractionDigits());
        System.out.println(us.format(new BigDecimal("1234.50")));
    }
}
~~~

Compile and run:

~~~bash
javac CurrencyInstanceDemo.java
java CurrencyInstanceDemo
~~~

Output on a JDK with common US locale data:

~~~text
USD
2
2
$1,234.50
~~~

`NumberFormat.getCurrencyInstance(Locale.US)` uses both the **formatting rules** and the **default currency** appropriate for the locale. However, a transaction in `EUR` should not be changed into USD just because the viewer has `Locale.US`.

**Important:** Currency symbols, Unicode whitespace, negative value representation, and certain patterns can vary across locales or JDK/CLDR versions. Do not turn a string example from one locale into a universal rule for all locales.

## 3. `Currency`: a currency code, not a locale

`java.util.Currency` represents a monetary unit by code, such as:

~~~java
Currency usd = Currency.getInstance("USD");
Currency eur = Currency.getInstance("EUR");
Currency jpy = Currency.getInstance("JPY");
Currency vnd = Currency.getInstance("VND");
~~~

This is a **snippet**, requiring `import java.util.Currency`. A currency is identified by its **code**, not by guessing from a user's name or a symbol like `$`. The `$` sign can belong to many currencies in many contexts; looking at the symbol alone is not enough to confirm the ISO currency code.

`Currency.getInstance("USD")` retrieves the object representing USD; it does not create a formatter and does not change any monetary value. If an invalid code is passed to this API, Java may throw `IllegalArgumentException`; therefore, input from APIs/users must be validated.

`Currency.getInstance(Locale.US)` can retrieve the currency of the country/region in the locale; that is a **regional default**, not always the currency stated on an invoice. Locales that do not specify an appropriate country may have no defined currency or may not be accepted by this lookup path; do not rely on it to infer the transaction currency.

### Currency code, symbol, and display name

- `getCurrencyCode()`: a more stable code for storing/transmitting data, for example `USD`.
- `getSymbol(locale)`: the symbol used when displaying to a reader in a specific locale; not a unique transaction identifier.
- `getDisplayName(locale)`: the localized display name if supported by runtime data.
- `getDefaultFractionDigits()`: the number of decimal digits commonly used when displaying the currency.

**Do not store only a formatted string** such as `"$1,234.50"` as the source monetary data; it depends on display formatting. Instead, store the **amount**, **currency code**, and required business metadata.

## 4. `setCurrency` changes the displayed unit, not the numeric value

Example:

~~~java
NumberFormat formatter =
        NumberFormat.getCurrencyInstance(Locale.US);

formatter.setCurrency(Currency.getInstance("EUR"));

String text = formatter.format(new BigDecimal("1234.50"));
~~~

This is a **snippet**, requiring imports for `NumberFormat`, `Locale`, `Currency`, and `BigDecimal`. On a formatter that supports currency formatting, `setCurrency` switches the currency metadata/symbol used for display to EUR within the presentation layout of `Locale.US`.

**It does not:**

1. Convert `1234.50 USD` into an equivalent EUR amount at an exchange rate.
2. Look up exchange rates.
3. Replace tax, discount, or accounting calculations.
4. Automatically update all fraction-digit settings on the formatter.
5. Change `Locale.US` into `Locale.GERMANY`.

If a number `1234.50` is actually USD, yet the code calls `setCurrency(EUR)` and formats that same number, the result will **label a USD amount as EUR** — a serious business logic bug. Only call `setCurrency` when **the unit of the numeric data is actually the attached currency**, or after the system has performed the proper conversion calculation.

## 5. The most easily overlooked detail: `setCurrency` does not automatically change fraction digits

Each currency has a different standard number of fraction digits:

- `USD` typically has 2 digits after the decimal point.
- `EUR` typically has 2 digits.
- `JPY` and `VND` typically have 0 digits according to JDK currency data.
- Some currencies have 3 fraction digits.

The key point in Java: calling `setCurrency(Currency)` **does not automatically adjust** `getMinimumFractionDigits()` and `getMaximumFractionDigits()` on an existing formatter.

Look at the example **`SetCurrencyDigitsDemo.java`**:

~~~java
import java.text.NumberFormat;
import java.util.Currency;
import java.util.Locale;

public class SetCurrencyDigitsDemo {
    public static void main(String[] args) {
        NumberFormat formatter =
                NumberFormat.getCurrencyInstance(Locale.US);

        Currency yen = Currency.getInstance("JPY");

        System.out.println("Before: " +
                formatter.getCurrency().getCurrencyCode() + " / " +
                formatter.getMinimumFractionDigits() + " / " +
                formatter.getMaximumFractionDigits());

        formatter.setCurrency(yen);

        System.out.println("After: " +
                formatter.getCurrency().getCurrencyCode() + " / " +
                formatter.getMinimumFractionDigits() + " / " +
                formatter.getMaximumFractionDigits());

        System.out.println("JPY standard digits: " +
                yen.getDefaultFractionDigits());

        int digits = yen.getDefaultFractionDigits();
        if (digits >= 0) {
            formatter.setMinimumFractionDigits(digits);
            formatter.setMaximumFractionDigits(digits);
        }

        System.out.println("Adjusted: " +
                formatter.getMinimumFractionDigits() + " / " +
                formatter.getMaximumFractionDigits());
    }
}
~~~

~~~bash
javac SetCurrencyDigitsDemo.java
java SetCurrencyDigitsDemo
~~~

Output on a common JDK:

~~~text
Before: USD / 2 / 2
After: JPY / 2 / 2
JPY standard digits: 0
Adjusted: 0 / 0
~~~

Explanation:

- The factory initially creates a US/`USD` currency formatter, with 2 fraction digits.
- `setCurrency(JPY)` changes the currency to JPY but **keeps 2/2 unchanged**.
- To default to **showing no fractional part** for JPY, the program reads `yen.getDefaultFractionDigits()` and sets both min and max to 0.

In the demonstration example, if you format `1234.5` **right after** `setCurrency(JPY)` but **before** adjusting the digits, the formatter can still display two fraction digits along with the JPY symbol. That differs from a formatter created from `Locale.JAPAN` from the start, which normally has 0 fraction digits for JPY.

**Why is there a `digits >= 0` check?** `Currency.getDefaultFractionDigits()` can return `-1` for codes that have no applicable fraction-digit rule. When encountering this situation, the application needs to decide its own rule rather than passing `-1` into setters without checking.

### Should you always force the currency's default?

No. `getDefaultFractionDigits()` is the **standard value** for the currency, not a replacement for every accounting rule. A system might need higher internal precision, or a securities/FX product might require 4–8 decimal places.

Separate:
- **Calculation/storage precision**: according to business rules.
- **Display precision**: according to currency, transaction type, and user requirements.
- **Rounding rules**: explicitly defined to avoid unintended repeated rounding.

## 6. Comparing creating a formatter for a locale's currency vs. changing the currency

Two cases:

~~~java
NumberFormat japan =
        NumberFormat.getCurrencyInstance(Locale.JAPAN);

NumberFormat usWithYen =
        NumberFormat.getCurrencyInstance(Locale.US);

usWithYen.setCurrency(Currency.getInstance("JPY"));
~~~

Both may carry `Currency JPY`, but they are **not completely equivalent in configuration**:

| Property | `getCurrencyInstance(Locale.JAPAN)` | `getCurrencyInstance(Locale.US)` then `setCurrency(JPY)` |
| --- | --- | --- |
| Locale context | Japan | US |
| Currency after creation/configuration | JPY | JPY |
| Common initial fraction digits | 0 | 2, still remains 2 after `setCurrency` |
| Separators, symbol placement | Follows Japanese pattern | Follows US pattern |
| Negative format/spacing | Follows Japanese locale data | Follows US locale data |

Therefore, **the same currency does not mean the same display style**. A US customer viewing a JPY amount may want symbol placement and grouping separators formatted in US English style, while a Japanese customer wants a different presentation.

When a business needs **formatting independent of the reader's locale and the transaction's currency**, design two separate parameters instead of trying to derive everything from a single `Locale`.

## 7. Example: designing a currency formatting function with two independent parameters

A service method should explicitly accept **amount**, **currency**, and **locale**, rather than reading the JVM-wide default.

Create **`CurrencyDisplayService.java`**:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.NumberFormat;
import java.util.Currency;
import java.util.Locale;

public class CurrencyDisplayService {
    public static String format(
            BigDecimal amount,
            Currency currency,
            Locale locale) {

        NumberFormat formatter =
                NumberFormat.getCurrencyInstance(locale);

        formatter.setCurrency(currency);

        int digits = currency.getDefaultFractionDigits();
        if (digits >= 0) {
            formatter.setMinimumFractionDigits(digits);
            formatter.setMaximumFractionDigits(digits);
        }

        formatter.setRoundingMode(RoundingMode.HALF_UP);
        return formatter.format(amount);
    }

    public static void main(String[] args) {
        Currency usd = Currency.getInstance("USD");
        Currency jpy = Currency.getInstance("JPY");

        BigDecimal amount = new BigDecimal("1234.50");

        System.out.println(format(amount, usd, Locale.US));
        System.out.println(format(amount, jpy, Locale.US)
                .endsWith(".50"));
    }
}
~~~

~~~bash
javac CurrencyDisplayService.java
java CurrencyDisplayService
~~~

Output with common US locale:

~~~text
$1,234.50
false
~~~

The second line only prints a **boolean** to demonstrate that JPY no longer has the `.50` suffix. The actual JPY symbol can depend on the locale and JDK/provider, so the example avoids hardcoding the yen symbol string in stdout.

**Understanding the method above accurately:** This is an illustrative **formatting** helper, not a conversion pipeline. It defaults to the policy of "display the standard number of fraction digits for the currency" and `HALF_UP`. If the business requires `HALF_EVEN`, keeping more digits, or displaying optional decimals, you must adjust the policy accordingly.

You can place display rules in a dedicated class, such as `MoneyDisplayPolicy`, instead of applying a single rounding mode to every business case.

## 8. How does `setCurrency` affect the symbol?

In Java's standard currency formatter implementations, `setCurrency` updates the currency that the formatter uses for display. With `DecimalFormat`, it also updates the currency-symbol-related representations in the managed `DecimalFormatSymbols`.

Some examples of the currency display part:

- With a US locale and USD currency, the output usually has the `$` sign before the number.
- With a German locale and EUR currency, the decimal separator is a comma, the grouping separator is usually a period, and the symbol usually comes after the number with an appropriate space.
- With a US locale but EUR currency, the formatter can still use **US-style ordering/separators**, with only the currency symbol/code changing.

Example **`CurrencyCodeDemo.java`**:

~~~java
import java.text.NumberFormat;
import java.util.Currency;
import java.util.Locale;

public class CurrencyCodeDemo {
    public static void main(String[] args) {
        NumberFormat us = NumberFormat.getCurrencyInstance(Locale.US);
        System.out.println(us.getCurrency().getCurrencyCode());

        us.setCurrency(Currency.getInstance("EUR"));
        System.out.println(us.getCurrency().getCurrencyCode());

        System.out.println(us.getMinimumFractionDigits());
        System.out.println(us.getMaximumFractionDigits());
    }
}
~~~

~~~bash
javac CurrencyCodeDemo.java
java CurrencyCodeDemo
~~~

Output:

~~~text
USD
EUR
2
2
~~~

The example chooses to print the **ISO currency code** instead of the `€` symbol so it does not depend on runtime locale data/Unicode details.

### A short symbol is not a unique currency code

The `$` sign can often refer to many different currencies. When information must be unambiguous across borders, an application can display the **ISO code** or currency name alongside it per design requirements, and always store the currency code separately. Never try to extract the currency code from a formatted string.

In source code, if you need to retrieve the symbol for a specific locale, you can use `currency.getSymbol(locale)`; to retrieve the code, use `currency.getCurrencyCode()`.

## 9. Using the default locale and the impact of `Locale.getDefault()`

If you call:

~~~java
NumberFormat formatter = NumberFormat.getCurrencyInstance();
~~~

Java selects the runtime's default formatting locale at the time the formatter is created (related to `Locale.Category.FORMAT`). As a result, output can differ if the JVM runs on another machine or if something in the program changes the default.

The call:

~~~java
NumberFormat formatter =
        NumberFormat.getCurrencyInstance(requestLocale);
~~~

takes `requestLocale`, a `Locale` variable determined per user/request. This is the explicit way to control the locale.

**Never call `Locale.setDefault(...)` per HTTP request to change currency display.** The default locale is shared state across the JVM, so two concurrent requests can conflict with each other. Changing the default also does not automatically update previously cached formatters.

If a user stores the language `vi-VN` but transacts in USD, the two pieces of information must enter the program separately: the display locale choice is `vi-VN`, and the transaction currency is `USD`. Do not infer that USD is VND just because the user has a Vietnamese locale.

## 10. Why is `setCurrency` not a foreign exchange conversion?

Suppose the data is:

~~~text
amount = 100.00
currency = USD
~~~

When calling:

~~~java
NumberFormat display =
        NumberFormat.getCurrencyInstance(Locale.US);
display.setCurrency(Currency.getInstance("EUR"));
System.out.println(display.format(100));
~~~

This is a **snippet** with appropriate imports. The result follows EUR currency display style, yet **the number 100 is still 100**; it does not become the EUR amount equivalent to 100 USD.

To **convert USD → EUR** accurately in business logic, you need:
1. Source and target currencies.
2. An exchange rate from a trusted source, effective date/time, rate type, and fees.
3. Calculation and rounding rules according to the product.
4. A value calculated using an appropriate numeric type, typically `BigDecimal`.
5. The target currency attached to **the actual converted result value**, and only then formatted.

Do not invent a hardcoded exchange rate just to "format"; the examples in this lesson intentionally do not perform currency conversion.

## 11. Rounding mode and `BigDecimal` when displaying money

`NumberFormat` can round when the number of decimal digits in the data exceeds the configured limit. For example, with a `Locale.US` currency formatter, the value `1234.565` requires three fraction digits, but a formatter displaying two digits must decide the result.

- `RoundingMode.HALF_EVEN`: at the exact midpoint, chooses the even last digit.
- `RoundingMode.HALF_UP`: at the exact midpoint, rounds up in magnitude.
- Other modes suit different business rules.

Create **`CurrencyRoundingDemo.java`**:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.NumberFormat;
import java.util.Locale;

public class CurrencyRoundingDemo {
    public static void main(String[] args) {
        NumberFormat f = NumberFormat.getCurrencyInstance(Locale.US);
        BigDecimal amount = new BigDecimal("1234.565");

        f.setRoundingMode(RoundingMode.HALF_EVEN);
        System.out.println(f.format(amount));

        f.setRoundingMode(RoundingMode.HALF_UP);
        System.out.println(f.format(amount));
    }
}
~~~

~~~bash
javac CurrencyRoundingDemo.java
java CurrencyRoundingDemo
~~~

Output for the US USD formatter:

~~~text
$1,234.56
$1,234.57
~~~

`BigDecimal("1234.565")` preserves the exact decimal value in the example. If you construct `new BigDecimal(1234.565)` from a `double`, the value may no longer sit at the exact midpoint due to binary representation; avoid that approach when teaching or processing money.

**Note:** Currency formatting only produces a string for display. Businesses usually must round at the appropriate step of the calculation, not just at render time. If business data has already been rounded according to one rule, you should not accidentally round it again differently without control.

## 12. Distinguishing min/max fraction digits from a currency's digit count

There are three concepts:

| Property | Question answered |
| --- | --- |
| `currency.getDefaultFractionDigits()` | How many fraction digits does the currency normally display? |
| `formatter.getMinimumFractionDigits()` | When displaying, at least how many fraction digits must be printed? |
| `formatter.getMaximumFractionDigits()` | When displaying, at most how many fraction digits are allowed before rounding? |

Suppose `JPY` has a default of 0. You can still configure a formatter with min 0 / max 2 when you need to represent fractional data under a special policy. Conversely, if you want to display JPY with no fractional part, set both min and max to 0.

Do not force every currency to 2 digits just because USD and EUR have 2. Other currencies may have 0 or 3 fraction digits; and specific commercial rules may differ from the ISO default digit count.

When changing both min and max, the code expression should be clear and verify a valid currency digit count:

~~~java
int digits = currency.getDefaultFractionDigits();
if (digits >= 0) {
    formatter.setMinimumFractionDigits(digits);
    formatter.setMaximumFractionDigits(digits);
}
~~~

This snippet uses already-created `formatter` and `currency` variables. If the project needs per-transaction fraction digits, pass a separate policy parameter instead of always taking the default.

## 13. Parsing currency strings: do not use as full-string validation by default

`NumberFormat.getCurrencyInstance(locale)` also has a `parse` method to read strings formatted according to the corresponding locale/currency. However, parsing has important limitations:

- The result of `parse` is a `Number`, not a `Money` object carrying a currency code and business rules.
- Formatted currency strings across locales may use special whitespace characters, parentheses for negative numbers, or different currency symbols.
- Parsing may accept a **valid prefix** and stop before remaining characters; never assume the entire input was validated.
- A currency symbol like `$` can be ambiguous without currency context.

Example checking the parser position:

~~~java
NumberFormat f = NumberFormat.getCurrencyInstance(Locale.US);
String input = "$1,234.50xxx";
ParsePosition pos = new ParsePosition(0);
Number n = f.parse(input, pos);

System.out.println(n);
System.out.println(pos.getIndex() == input.length());
~~~

This is an **in-method snippet**, requiring imports `java.text.NumberFormat`, `java.text.ParsePosition`, and `java.util.Locale`. With a common US JDK locale, the parser reads the leading part and can leave the suffix behind; the boolean result must not be assumed to be true. To validate, check `n != null`, `pos.getErrorIndex()`, and `pos.getIndex() == input.length()`.

For payment APIs, a sturdier approach is usually to accept **a normalized number and a separate currency code** (for example in a DTO), validate them, and then format only at the presentation layer. Do not rely on user-facing display strings as trusted calculation data.

## 14. Should you cast to `DecimalFormat`?

In common JDKs, `getCurrencyInstance` usually returns a `DecimalFormat` object. That allows customizing patterns or `DecimalFormatSymbols`:

~~~java
NumberFormat general =
        NumberFormat.getCurrencyInstance(Locale.US);

if (general instanceof DecimalFormat decimal) {
    // You can configure DecimalFormat-specific features.
    System.out.println(decimal.toPattern());
}
~~~

This is a **snippet**, requiring imports for `NumberFormat`, `DecimalFormat`, and `Locale`. The `instanceof ... decimal` syntax is a pattern variable supported in Java 17+.

**Do not cast unconditionally** just to call `setCurrency`, because `setCurrency` is already on `NumberFormat`. In environments with custom locale service providers or other formatter classes, a hard cast can throw `ClassCastException`. Only use `DecimalFormat`-specific features when needed and after checking the implementation type.

If using a pattern like `¤#,##0.00` in `DecimalFormat`, the `¤` character relates to currency display. However, editing the pattern can change symbol placement and fraction-digit counts, and does not replace the currency/locale policy defined by the product.

## 15. Thread safety and formatter lifecycle

`NumberFormat` and `DecimalFormat` are **mutable** formatters and are not guaranteed to be safe when the same instance is accessed concurrently from multiple threads without synchronization. `setCurrency` is also a **state-mutating** operation.

The following code is very error-prone in an HTTP server:

~~~java
// Example that should NOT be shared across multiple requests:
static final NumberFormat SHARED =
        NumberFormat.getCurrencyInstance(Locale.US);
~~~

If request A calls `SHARED.setCurrency(USD)` and then request B calls `SHARED.setCurrency(EUR)` before A formats, A can receive a string with B's currency symbol. If min/max fraction digits, rounding mode, and patterns are modified concurrently as well, the results become even more unpredictable.

Safe options:

1. **Create a new instance per use** or per request. This approach is clear and usually a good starting point.
2. If caching, prefer caching **immutable configuration** (locale, currency, rounding policy, fraction digits) and creating the mutable formatter when used.
3. If you truly share an instance, you must synchronize the entire sequence of configuration + formatting operations, though this design easily becomes a bottleneck and needs benchmarking.
4. You can consider cloning a configured formatter or using a per-thread mechanism, with a clear lifecycle policy to avoid leaking request context between tasks.

Do not use `Locale.setDefault(...)` to change currency for concurrent requests. The default locale is shared state, and changing the default does not automatically change all already-created formatters.

## 16. Common mistakes

| Mistake | Why it is wrong | Correct approach |
| --- | --- | --- |
| Using `getCurrencyInstance(Locale.US)` and assuming all numbers are USD | Locale only specifies the initial configuration | Pass the transaction's actual currency |
| Calling `setCurrency(EUR)` to "convert USD to EUR" | There is no exchange-rate multiplication | Convert in business logic first, format afterward |
| Calling `setCurrency(JPY)` and thinking decimals automatically become 0 | Min/max fraction digits remain unchanged | Set min/max according to an explicit policy |
| Displaying 2 digits for every currency | Some currencies have 0 or 3 fraction digits | Check `getDefaultFractionDigits()` and business requirements |
| Storing `"$1,234.50"` as the source money value | Depends on locale, separators, and symbol | Store amount + currency code |
| Parsing formatted text to recover the currency code | `Number` does not carry a currency unit | Store/look up the currency code independently |
| Using `double` to represent prices requiring precision | Binary rounding error can affect calculations | Consider `BigDecimal` |
| Hardcoding `$` for all USD across all locales | Symbol/spacing can change | Use a formatter with an explicit locale |
| Sharing a mutable `NumberFormat` across multiple threads | Can cause race conditions and currency leaks | Create separate formatters or synchronize strictly |
| Changing the JVM default on each request | Shared JVM state | Pass `Locale` explicitly |

One particularly dangerous bug: **the wrong currency unit, yet the string still looks valid**. `€1,234.50` looks like a normal monetary amount, yet if the number is actually unconverted USD, the bug lies in the data and business logic, not in the formatter.

## 17. Practical testing checklist

You should have the following tests:

- **Initialization by locale:** `Locale.US` chooses USD and formats numbers in US style; `Locale.JAPAN` chooses JPY and a different standard fraction-digit count.
- **Changing currency:** from a USD formatter to JPY via `setCurrency`, verify that the currency code changes while fraction digits **do not automatically change**.
- **Applying policy:** after setting min/max for JPY, verify that the fractional part is handled as expected.
- **Different locale, same currency:** USD is displayed differently in `en-US` and `de-DE`; the numeric value does not change.
- **Same locale, different currency:** `en-US` can display USD and EUR, but the actual currency must be clearly distinguished.
- **Rounding boundary:** test `1.005`, `1.015`, or exact values with `BigDecimal` to verify the rounding mode.
- **Null/invalid currency:** validate inputs and avoid confusing error messages from misconfiguration.
- **ISO code:** store and return the exact currency code for the transaction.
- **Concurrency:** two requests using different currencies do not mutate each other's formatter.
- **Parse:** if accepting display strings as input, verify that the entire string is consumed and separators match the locale.
- **Runtime data:** when upgrading JDK/providers, evaluate changes in symbols, Unicode spaces, symbol placement, and digit counts.

For localized string snapshot tests, pin or control the JDK/locale provider version. Do not treat a regular space character (`U+0020`) as identical to a non-breaking space (`U+00A0`) or a narrow non-breaking space (`U+202F`).

## 18. Exercises with answers

**Question 1.** Which currency does `NumberFormat.getCurrencyInstance(Locale.US)` normally choose?

**Answer:** `USD`, according to the default convention of the US locale. This is the **initial** currency, not necessarily the currency of a specific invoice.

**Question 2.** Call `formatter.setCurrency(Currency.getInstance("JPY"))` on a USD formatter with min/max=2. Afterward, do min/max automatically become 0?

**Answer:** **No**. `setCurrency` does not automatically update fraction-digit counts. You must configure them according to display requirements.

**Question 3.** If a user uses German but pays in USD, which locale and currency should be used?

**Answer:** Choose the reader's locale, for example `Locale.GERMANY`, and the transaction currency `USD`; do not automatically change USD to EUR.

**Question 4.** Does `setCurrency(EUR)` automatically fetch the USD/EUR exchange rate?

**Answer:** No. It only changes the unit used for **display**, performing no conversion.

**Question 5.** Why should you store `Currency.getCurrencyCode()` instead of just the `$` symbol?

**Answer:** Symbols can be ambiguous across multiple currencies; the ISO code identifies the transaction unit much more clearly.

**Question 6.** Two requests share the same `NumberFormat` and call `setCurrency` with different currencies. What is the risk?

**Answer:** The mutable formatter can be modified between operations of the two threads, causing one request to display the other request's currency.

**Question 7.** If `getDefaultFractionDigits()` returns `-1`, should you force min/max to that value?

**Answer:** Do not apply it mechanically. You must choose a display policy appropriate for that currency/business case.

**Question 8.** Why is `BigDecimal("1234.565")` better suited for testing rounding than `new BigDecimal(1234.565)`?

**Answer:** The string constructor preserves the exact decimal number; the `double` constructor can carry binary representation error.

## 19. Summary

You can remember the usage flow as follows:

~~~text
Base amount + Currency code + Reader's locale
              |
              v
NumberFormat.getCurrencyInstance(locale)
              |
              v
formatter.setCurrency(currency)
              |
              v
Choose appropriate fraction digits + rounding policy
              |
              v
formatter.format(amount)
              |
              v
Display string according to actual locale and currency
~~~

**The three most important principles:**

1. **`getCurrencyInstance(locale)` determines the initial display configuration for the locale.**
2. **`setCurrency(currency)` changes the currency but does not convert the value and does not automatically adjust min/max fraction digits.**
3. **The transaction's currency, the reader's locale, and the rounding policy are separate facts**; pass them explicitly to avoid monetary bugs in real-world applications.

Java SE 17 Documentation: [NumberFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html), [Currency](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Currency.html), [DecimalFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormat.html).
