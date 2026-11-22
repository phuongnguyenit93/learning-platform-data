# Currency, Currency Codes, and Display Locales in Java

## 1. A Monetary Amount Has Two Independent Pieces of Information

Suppose the system records **1,234.50 USD**. A viewer in the United States might see `$1,234.50`, while a viewer in Germany might see `1.234,50 $`. Both are viewing **the same amount in USD**, rather than the system having converted it to EUR.

In Java, you need to distinguish:

- **`java.util.Currency`**: describes the **currency unit**, typically identified by an ISO 4217 code such as `USD`, `EUR`, `JPY`, `VND`.
- **`java.util.Locale`**: describes the reader's **display conventions**, such as grouping separators, decimal separators, currency symbols, and symbol placement.
- **`java.text.NumberFormat`**: formats a **numeric value** into a currency string according to the configured locale and currency.
- **`BigDecimal`**: the numeric type typically suited for monetary values that require exact decimal arithmetic.

The three aspects to manage separately are **amount**, **currency**, and **display locale**.

| Amount | Currency | Display locale | Typical output |
| ---: | --- | --- | --- |
| `1234.50` | `USD` | `en-US` | `$1,234.50` |
| `1234.50` | `USD` | `de-DE` | `1.234,50 $` |
| `1234.50` | `EUR` | `de-DE` | `1.234,50 €` |
| `1234` | `JPY` | `ja-JP` | `￥1,234` or an equivalent yen symbol depending on the JDK/provider |

The exact output depends on locale data, JDK, and provider. For example, the currency symbol may be `$`, `US$`, `USD`, or another character depending on context; the space before the symbol may be **NBSP** (`U+00A0`) or a special whitespace character. You should not write tests relying on the exact symbol appearance across all locales unless you control the runtime environment.

**Key takeaway:** `Locale.GERMANY` **does not turn** a `USD` amount into `EUR`. It only provides formatting conventions for presentation. Changing the currency unit is a separate **currency conversion business operation** that requires an exchange rate, effective timestamp, and rounding rules.

## 2. What Is `Currency`? What Do ISO 4217 Codes Mean?

`java.util.Currency` represents a currency unit according to the currency data provided by the JDK. This object is **immutable**. The standard way to obtain an instance is:

~~~java
Currency usd = Currency.getInstance("USD");
Currency eur = Currency.getInstance("EUR");
Currency jpy = Currency.getInstance("JPY");
Currency vnd = Currency.getInstance("VND");
~~~

The snippet above is a **method-body code fragment** and requires `import java.util.Currency;`.

### 2.1. Currency Codes Are Not Country Codes

For example:

| Code | Currency unit | Related country/region code in example |
| --- | --- | --- |
| `USD` | US dollar | `US` |
| `EUR` | Euro | `DE` and many countries in the eurozone |
| `JPY` | Japanese yen | `JP` |
| `VND` | Vietnamese đồng | `VN` |

`USD` and `EUR` are ISO 4217 **currency codes**. `US`, `DE`, `JP`, and `VN` are **region codes** in locales. They serve different purposes and **cannot be used interchangeably**.

Incorrect example:

~~~java
// Wrong: "US" is a region code, not an ISO 4217 currency code.
Currency wrong = Currency.getInstance("US");
~~~

This call can throw `IllegalArgumentException` because the code is invalid. Similarly, you cannot construct a locale with the code `USD` and expect it to properly represent a viewer.

### 2.2. Useful Methods

| API | Value/responsibility |
| --- | --- |
| `Currency.getInstance("USD")` | Obtains the currency by ISO 4217 code |
| `Currency.getInstance(locale)` | Obtains the currency associated with the locale's region, if available |
| `getCurrencyCode()` | Returns the three-letter code, e.g., `USD` |
| `getNumericCode()` | Returns the ISO 4217 numeric code, e.g., `840` for USD |
| `getDefaultFractionDigits()` | Default number of fraction digits for the currency unit; may be `-1` for certain special codes |
| `getSymbol(locale)` | Currency symbol appropriate for the passed locale |
| `getDisplayName(locale)` | Display name of the currency in the language/locale |
| `Currency.getAvailableCurrencies()` | Set of currencies known to the JDK |

`getNumericCode()` returns an `int`, so if you need to exchange a **three-digit ISO numeric code**, you must handle zero-padding according to the protocol specification rather than assuming an `int` preserves leading zeros.

**Do not use `getDefaultFractionDigits()` as the "single accounting rule"**: it is metadata for the default number of fraction digits, not every rule regarding cash settlement, wire transfers, pricing, taxes, deductions, or rounding. For instance, a transaction may require a different precision depending on the financial system, even with the same currency code.

## 3. Creating Currency by Code vs. by Locale

The following two calls serve different purposes:

~~~java
Currency byCode = Currency.getInstance("USD");
Currency byRegion = Currency.getInstance(Locale.GERMANY);
~~~

The snippet above requires importing `java.util.Currency` and `java.util.Locale`.

- `getInstance("USD")` selects **the exact USD currency** recognized by the data.
- `getInstance(Locale.GERMANY)` selects the currency associated with **region DE**, which is normally `EUR`.
- A locale may lack a country or belong to a region without a valid currency. Never assume every `Locale` produces a `Currency`; the API may throw `IllegalArgumentException` when the region is missing, or return `null` for regions with no currency in the JDK data.

In particular, obtaining a currency from a locale is only appropriate when **the business requirement is genuinely "the default currency of this region."** It is not appropriate when the transaction already has a currency code.

For example, the same viewer with `Locale.GERMANY` can receive invoices in `USD`, `EUR`, or `JPY`. **Keep the transaction's currency in the data** instead of inferring it incorrectly from the viewer's location or language.

## 4. Complete Example: Reading Code, Numeric Code, and Default Fraction Digits

Save as `CurrencyIdentityDemo.java`:

~~~java
import java.util.Currency;
import java.util.Locale;

public class CurrencyIdentityDemo {
    public static void main(String[] args) {
        Currency usd = Currency.getInstance("USD");
        Currency jpy = Currency.getInstance("JPY");

        System.out.println("USD code: " + usd.getCurrencyCode());
        System.out.println("USD numeric: " + usd.getNumericCode());
        System.out.println("USD digits: " + usd.getDefaultFractionDigits());

        System.out.println("JPY code: " + jpy.getCurrencyCode());
        System.out.println("JPY digits: " + jpy.getDefaultFractionDigits());

        System.out.println("DE default: "
                + Currency.getInstance(Locale.GERMANY).getCurrencyCode());
        System.out.println("JP default: "
                + Currency.getInstance(Locale.JAPAN).getCurrencyCode());
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac -encoding UTF-8 CurrencyIdentityDemo.java
java CurrencyIdentityDemo
~~~

On standard JDK ISO 4217 data, the output is:

~~~text
USD code: USD
USD numeric: 840
USD digits: 2
JPY code: JPY
JPY digits: 0
DE default: EUR
JP default: JPY
~~~

Interpretation:

- `Currency.getInstance("USD")` does not depend on the display locale.
- `getNumericCode()` provides the standard numeric code of the currency, **not** an exchange rate or monetary amount.
- `USD` normally has two default fraction digits, while `JPY` has zero default fraction digits.
- The default currency from `Locale.GERMANY` is `EUR` and from `Locale.JAPAN` is `JPY` according to current data.

JDK currency data can be updated when a country changes its currency or ISO rules change. For business logic sensitive to transaction history, explicitly store the currency code and transaction date; do not infer it from a locale at display time.

## 5. Same Currency, Multiple Display Locales

This is the most common scenario in multilingual applications: **the amount and currency unit do not change**, but different viewers see different grouping separators, decimal separators, and symbols.

### Complete Java 17+ Example

Create `CurrencyDisplayDemo.java`:

~~~java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.util.Currency;
import java.util.Locale;

public class CurrencyDisplayDemo {
    public static void main(String[] args) {
        BigDecimal amount = new BigDecimal("1234.50");
        Currency currency = Currency.getInstance("USD");

        NumberFormat forUS =
                NumberFormat.getCurrencyInstance(Locale.US);
        forUS.setCurrency(currency);
        forUS.setMinimumFractionDigits(2);
        forUS.setMaximumFractionDigits(2);

        NumberFormat forGermany =
                NumberFormat.getCurrencyInstance(Locale.GERMANY);
        forGermany.setCurrency(currency);
        forGermany.setMinimumFractionDigits(2);
        forGermany.setMaximumFractionDigits(2);

        System.out.println("Amount: " + amount.toPlainString());
        System.out.println("Currency: " + currency.getCurrencyCode());
        System.out.println("US view: " + forUS.format(amount));
        System.out.println("DE view: " + forGermany.format(amount));
        System.out.println("Still USD: " + currency.getCurrencyCode());
    }
}
~~~

Run commands:

~~~bash
javac -encoding UTF-8 CurrencyDisplayDemo.java
java CurrencyDisplayDemo
~~~

Illustrative output with a common JDK/CLDR provider:

~~~text
Amount: 1234.50
Currency: USD
US view: $1,234.50
DE view: 1.234,50 $
Still USD: USD
~~~

**Unicode note:** The space before the `$` sign on the German line above is a non-breaking space `U+00A0` (NBSP), not a regular ASCII space. Symbols and spacing may differ on other environments/providers. If automated tests need exact string comparisons, know which JDK/provider version is in use and check code points rather than relying on visual inspection.

Steps in the code:

1. `amount` is the monetary amount, stored as a `BigDecimal`.
2. `currency` is always `USD`, determined from the currency code.
3. Two `NumberFormat` instances are created from **two different display locales**.
4. `setCurrency(currency)` applies USD to each formatter.
5. The two formatters produce two different presentation strings, while `amount` and `currency` remain unchanged.

**Rule:** Do not manually format currency by string concatenation such as `"$" + amount` or `amount + " USD"` unless a protocol or design requires a fixed format. Symbol placement, spacing, signs, and digit conventions are locale concerns.

## 6. Does `NumberFormat.getCurrencyInstance(locale)` Choose a Currency Automatically?

Yes. When you call:

~~~java
NumberFormat formatter =
        NumberFormat.getCurrencyInstance(Locale.GERMANY);
~~~

The formatter defaults to that locale's currency conventions, typically `EUR` for `de-DE`. However, this is only right when the application wants to **display the region's default currency**; it is not automatically right for a USD transaction.

For a transaction with its own currency code, you must set it explicitly:

~~~java
NumberFormat formatter =
        NumberFormat.getCurrencyInstance(Locale.GERMANY);
formatter.setCurrency(Currency.getInstance("USD"));
~~~

**Important:** `setCurrency(...)` changes the currency that the formatter uses when producing the currency symbol and related metadata. Per the API contract, **it does not necessarily update the formatter's minimum/maximum fraction digits**. Those properties may retain the settings from when the formatter was created.

### 6.1. Why `setCurrency` Is Not Enough to Change Precision

Try the program `CurrencyDigitsDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.NumberFormat;
import java.util.Currency;
import java.util.Locale;

public class CurrencyDigitsDemo {
    public static void main(String[] args) {
        Currency jpy = Currency.getInstance("JPY");
        NumberFormat format =
                NumberFormat.getCurrencyInstance(Locale.US);

        format.setCurrency(jpy);
        System.out.println("Digits after setCurrency: "
                + format.getMaximumFractionDigits());

        format.setMinimumFractionDigits(jpy.getDefaultFractionDigits());
        format.setMaximumFractionDigits(jpy.getDefaultFractionDigits());
        format.setRoundingMode(RoundingMode.HALF_UP);

        System.out.println("Digits after configuration: "
                + format.getMaximumFractionDigits());
        System.out.println("JPY amount: "
                + format.format(new BigDecimal("1234.50")));
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 CurrencyDigitsDemo.java
java CurrencyDigitsDemo
~~~

With a common JDK/provider, the output is:

~~~text
Digits after setCurrency: 2
Digits after configuration: 0
JPY amount: ¥1,235
~~~

Explanation:

- A formatter created from `Locale.US` initially has a currency precision of typically **two** fraction digits (default USD currency).
- Calling `setCurrency(JPY)` does not automatically change the fraction digit limits.
- Next, the code explicitly sets the fraction digits according to `jpy.getDefaultFractionDigits()` (typically `0`).
- `RoundingMode.HALF_UP` makes explicit how `1234.50 → 1235` is handled when displaying with no decimal part.

The displayed yen symbol may vary in Unicode form or depending on locale data. Do not treat the `¥` symbol as a unique identifier of a currency; Japanese yen and certain other currencies can use visually similar symbols.

**For currencies returning `getDefaultFractionDigits() == -1`:** Do not directly call `setMinimumFractionDigits(-1)` or `setMaximumFractionDigits(-1)`; those methods require non-negative values. Define a custom precision rule or fallback policy for special codes. For payment applications, the number of fraction digits must come from **specific business rules**, not simply from the JDK's presentation defaults.

## 7. `Currency.getSymbol(locale)` and `getDisplayName(locale)`

These two methods use a locale to represent **the same currency**:

~~~java
Currency usd = Currency.getInstance("USD");

String code = usd.getCurrencyCode();               // "USD"
String usSymbol = usd.getSymbol(Locale.US);        // typically "$"
String germanSymbol = usd.getSymbol(Locale.GERMANY);
String germanName = usd.getDisplayName(Locale.GERMANY);
~~~

The snippet above requires importing `java.util.Currency` and `java.util.Locale`, and must be placed inside a method.

- `getCurrencyCode()`: stable code used to **identify** the currency unit.
- `getSymbol(locale)`: symbol for **presentation** according to the locale.
- `getDisplayName(locale)`: name for **presentation** in the reader's language.

On a JDK with German CLDR data, the name for `USD` may be rendered as `US-Dollar`; the symbol may be `$` or a disambiguated form like `US$` depending on data/provider. These strings are UI display data that can be updated, **not identifiers for storing transactions**.

Do not use `getSymbol()` as a system key, because a symbol such as `$` is used by many currencies. Do not parse a string containing `$` and assume it is USD if the system accepts Canadian dollars, Australian dollars, or other currencies.

## 8. Currency Unit Differs from Locale and Differs from Foreign Exchange Conversion

Suppose the system holds an amount:

~~~text
amount = 100.00
currency = USD
displayLocale = de-DE
~~~

Code:

~~~java
NumberFormat format =
        NumberFormat.getCurrencyInstance(Locale.GERMANY);
format.setCurrency(Currency.getInstance("EUR"));
String text = format.format(new BigDecimal("100.00"));
~~~

This is an **illustrative code snippet** inside a method; it requires importing `java.text.NumberFormat`, `java.util.Currency`, `java.util.Locale`, and `java.math.BigDecimal`.

This snippet merely makes the formatter display **100 EUR**; it **does not** convert `100 USD` into an equivalent EUR amount. If the original `100` was USD, printing it with the EUR symbol states the **wrong unit**.

### Currency Conversion Is a Separate Problem

To convert:

\[
\text{amount}_{EUR}
=
\text{amount}_{USD}
\times
\text{rate}_{USD \rightarrow EUR}
\]

You need an exchange rate obtained from an authoritative source for the business domain, the effective timestamp of the rate, a rounding policy, and transaction recording rules. Java SE does not provide a `Currency.convert(...)` function or an automatic live exchange rate inside `java.util.Currency`.

Illustrative example **using only a hypothetical exchange rate, not a real market quote**:

~~~java
BigDecimal usdAmount = new BigDecimal("100.00");
BigDecimal exampleRate = new BigDecimal("0.90"); // Hypothetical exchange rate
BigDecimal eurAmount = usdAmount.multiply(exampleRate);
System.out.println(eurAmount.toPlainString()); // 90.0000
~~~

The snippet above is a method-body fragment requiring `import java.math.BigDecimal`. The result of multiplication here may retain scale from the operands; in the example above, two `BigDecimal` values with scale 2 produce `100.00 × 0.90 = 90.0000`. Only afterward should you apply business rounding/scale rules for the EUR amount, and **only at the end** format it for display.

**Do not confuse "changing the symbol" with "converting the unit."** A safe design is to bundle `amount` and `currencyCode` in the same domain object so you cannot accidentally change only the display symbol while forgetting to convert the number.

## 9. Choosing a Monetary Storage Type: BigDecimal and Currency Code

Java SE does not include a universal monetary value type that combines amount, Currency, arithmetic operations, exchange rates, and business rules. `Currency` only describes the currency unit; **it does not hold a monetary amount**.

A simple data design:

~~~java
import java.math.BigDecimal;
import java.util.Currency;
import java.util.Objects;

public record Money(BigDecimal amount, Currency currency) {
    public Money {
        Objects.requireNonNull(amount, "amount");
        Objects.requireNonNull(currency, "currency");
    }
}
~~~

Save as `Money.java`. With a Java 17 record, the program can instantiate:

~~~java
Money invoice = new Money(
        new BigDecimal("1234.50"),
        Currency.getInstance("USD")
);
~~~

This is a **method-body code fragment** using the `Money` class defined above; import `java.math.BigDecimal` and `java.util.Currency`.

Advantages:

- Amount and currency travel together, preventing a USD amount from being confused with EUR.
- Addition/subtraction operations can check currency compatibility before executing.
- The program explicitly decides when conversion takes place.
- The display locale is passed separately into the UI layer rather than being fixed inside the record.

**Must be extended according to real business rules:** adding two `Money` values of different currencies must be rejected or routed through a controlled conversion step. For payments, rounding and precision rules must be explicitly specified. `BigDecimal` does not automatically solve issues such as cash rounding, legal regulations, transaction dates, or valid scales for each payment method.

### Example of Proper Boundary Modeling

~~~text
Transaction data:
  amount       = 1234.50
  currencyCode = USD
          |
          v
  Currency.getInstance("USD")
          |
          +-----------------------------+
          |                             |
          v                             v
Display locale = en-US        Display locale = de-DE
          |                             |
          v                             v
  $1,234.50                  1.234,50 $ (example)
          \                             /
           \___________________________/
                Still 1234.50 USD
~~~

Adding a `locale` at the presentation layer **does not** alter the transaction's currency in the data.

## 10. Parsing Currency Strings and Identifying the Currency Unit

`NumberFormat.getCurrencyInstance(locale)` can be used to parse a string according to locale conventions:

~~~java
NumberFormat parser =
        NumberFormat.getCurrencyInstance(Locale.US);
Number number = parser.parse("$1,234.50");
~~~

This is a method-body fragment requiring `import java.text.NumberFormat` and `java.util.Locale`; `parse` can throw `ParseException`, so the exception must be caught or declared.

However, **do not treat `NumberFormat.parse(...)` as a step that validates a transaction's currency code**. It can read a numeric value matching the formatter's pattern, but it does not on its own produce an independently validated business record `(amount, currencyCode)`.

For example, the string `"$1,234.50"` **is not a reliable currency identifier** because `$` can be used across multiple currency systems. Business data sources should pass the ISO 4217 code **separately** from the amount.

### If a UI Parser Is Needed

1. Know in advance the **currencyCode** allowed by the form, e.g., `USD`.
2. Know the user's **displayLocale** to correctly read grouping separators, decimal separators, and digits.
3. Use the appropriate formatter/parser and verify that **the entire string was consumed**.
4. Validate value constraints: non-negative or negative allowed, limits, precision, transaction date.
5. Never infer currency solely from a display symbol.

You can use `ParsePosition` to check that the valid prefix spans the entire input:

~~~java
ParsePosition position = new ParsePosition(0);
Number parsed = parser.parse(input, position);

if (parsed == null || position.getIndex() != input.length()) {
    throw new IllegalArgumentException("Invalid currency input");
}
~~~

This is an **illustrative code fragment** inside a method; it requires `import java.text.ParsePosition`, with `parser` already defined as a `NumberFormat` and `input` as the string to validate. Verifying full consumption of the input is necessary, though it **does not guarantee** that the parser has checked all business rules or confirmed the currency code. For machine-to-machine APIs, prefer passing `amount` and `currencyCode` as two explicit fields rather than using localized currency strings as the interchange format.

### `DecimalFormat.setParseBigDecimal(true)`

To parse decimal numbers with better precision, when the formatter is actually a `DecimalFormat`, you can configure:

~~~java
DecimalFormat parser = (DecimalFormat)
        NumberFormat.getCurrencyInstance(Locale.US);
parser.setParseBigDecimal(true);
~~~

This fragment requires importing `java.text.DecimalFormat`, `java.text.NumberFormat`, and `java.util.Locale`. **Do not assume every `NumberFormat` implementation is necessarily a `DecimalFormat`**. If you cast in code that must run across multiple providers/JDKs, check the runtime type or build a parser tailored to your system. `setParseBigDecimal` does not automatically validate the currency code.

## 11. Common Mistakes

| Misconception | Consequence | Correct approach |
| --- | --- | --- |
| "Locale is the currency." | Picks the wrong currency for an invoice | Store the transaction's currencyCode and displayLocale separately |
| "`Locale.GERMANY` means every invoice is in EUR." | Mistakenly turns USD units into EUR | `getCurrencyInstance(Locale.GERMANY)` only picks the region's default currency |
| "Calling `setCurrency(EUR)` converts USD to EUR." | Keeps the same numeric amount while changing the symbol, causing a unit error | Actual conversion requires an exchange rate and a separate calculation |
| "Every currency has two decimal places." | Wrong for JPY and other currencies | Check `getDefaultFractionDigits()` together with business rules |
| "`setCurrency` always updates fraction digits." | May display JPY with two decimal places | Set min/max fraction digits explicitly when needed |
| "The `$` symbol uniquely identifies USD." | Confused with CAD, AUD, and other currencies | Store and exchange ISO 4217 codes |
| "`NumberFormat.parse` returns an accurate amount and currency." | Cannot verify the transaction's currency code | Parse the amount by locale and validate currencyCode separately |
| "`double` is always accurate enough for money." | Can introduce binary floating-point rounding errors | Consider `BigDecimal` and explicit rounding rules |
| "Calling `Currency.getInstance(Locale)` always returns a result." | Locale may lack a country or belong to a region without a currency | Check preconditions and handle `null`/exceptions per the API |
| "Using currency symbols in logs/APIs is fine." | Symbols/locales change, making data hard to parse | Transmit amount and currencyCode in a consistent protocol |
| "Sharing one `NumberFormat` across all requests is safe." | Mutable state can be corrupted across threads | Create/copy formatters per request or synchronize appropriately |
| "A currency code embeds an exchange rate." | Incorrect conversion math | Exchange rates are independent data with an effective timestamp |

## 12. Application and Testing Checklist

**When designing models and APIs:**

- Store **amount** and **currencyCode** explicitly, such as `1234.50` and `"USD"`.
- Consider `BigDecimal` for money; explicitly specify scale, rounding, and precision at business boundaries.
- Separate the **display locale** from the transaction's currency.
- If choosing a currency automatically by region, document clearly that it is the region's default currency and handle cases where none exists.
- Do not allow changing a currency in the model merely by modifying a formatter's symbol.

**When formatting:**

- Call `NumberFormat.getCurrencyInstance(displayLocale)`.
- If the transaction currency is known, call `setCurrency(currency)`.
- Configure fraction digits and rounding as required; do not assume `setCurrency` changes everything automatically.
- Test across locales `en-US`, `de-DE`, `vi-VN`, and at least currencies with different fraction digits, such as USD/JPY.
- Ensure the code does not depend on the server's `Locale.getDefault()` when a user locale is available.
- Inspect Unicode characters in the output if exact string matching is required.

**When processing data:**

- Do not parse a display string to extract the currency code if the system has a dedicated `currencyCode` field.
- Do not store formatted strings like `"1.234,50 $"` in place of `amount` and `code` in the primary database.
- When converting currencies, record the exchange rate source, timestamp, and calculation rules.
- If an API accepts a currency code from a user, validate it with `Currency.getInstance(code)` and against the product's allowed currency policy.

## 13. Self-Check Exercises

1. Create `Currency.getInstance("USD")`, and print `getCurrencyCode()`, `getNumericCode()`, and `getDefaultFractionDigits()`. Why are these three values distinct from `Locale.US`?
2. A user with `Locale.GERMANY` wants to view a balance of `1234.50 USD`. Use `NumberFormat.getCurrencyInstance(Locale.GERMANY)` followed by `setCurrency(USD)`; explain why it must not be turned into EUR without an exchange rate.
3. Create a formatter from `Locale.US`, call `setCurrency(JPY)`, and check `getMaximumFractionDigits()` before and after configuring `getDefaultFractionDigits()`. Why should precision be specified explicitly?
4. Explain why `Currency.getSymbol(Locale.US)` cannot replace `getCurrencyCode()` in a transaction storage schema.
5. Design a `Money` class/record containing `amount` and `currency`. Write a validation rule for adding two amounts with different currencies.
6. Given a **hypothetical** exchange rate of 1 USD = 0.90 EUR, for an amount of `100.00 USD`, compute the EUR value using `BigDecimal` and distinguish the **amount conversion** step from the **result formatting** step.
7. Why should you not parse `"$1,234.50"` to infer the USD unit automatically? If the data comes from a form, what additional information do you need?
8. Test the same `Money(1234.50, USD)` on `Locale.US` and `Locale.GERMANY`. Which attributes are allowed to differ, and which must remain invariant?

**Remember:** `Currency` identifies the **currency unit** via codes like `USD` or `EUR`; `Locale` determines the **display conventions**; `NumberFormat` combines both to produce a currency string. **Changing the currency on a formatter is not an exchange-rate conversion**, and **changing the locale does not change an amount's currency unit**. Keep amount, currency code, and display locale separate, use `BigDecimal` when precision is required, and configure precision/rounding appropriately.

### References

- [Java SE 17 — Currency](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Currency.html) — ISO 4217 codes, display symbols/names, and default fraction digits.
- [Java SE 17 — NumberFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html) — `getCurrencyInstance`, `setCurrency`, and locale-aware formatting and parsing.
- [Java SE 17 — DecimalFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormat.html) — pattern rules, fraction digits, and decimal number parsing.
- [Java SE 17 — BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html) — decimal numeric values and rounding rules.