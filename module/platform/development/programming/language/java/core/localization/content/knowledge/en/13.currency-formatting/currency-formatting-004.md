# Distinguishing Currency Units from Locale Presentation Conventions

## 1. Two different questions: how much money, and how to display it?

Suppose an invoice has an amount of **1,234.50 USD** and is shown to two users:

- A user in the United States might see `$1,234.50`.
- A user using German conventions might see `1.234,50 $` (possibly with a non-breaking space between the number and the symbol).

This is **the same amount of 1,234.50 US dollars**, not two different amounts of money. Separators, symbol placement, and whitespace change according to presentation conventions; **the USD currency unit does not change**.

Conversely, `100 USD` and `100 EUR` are **two amounts carrying different units** even though both have the numeric part `100`. Changing separators or swapping the outer symbol cannot turn USD into EUR. Converting a currency unit requires explicit **exchange rates, rate timestamps, rounding rules, and business logic**.

In Java, these two concepts are represented separately:

- `java.util.Currency`: identifies the **currency unit**, such as `USD`, `EUR`, `JPY`, `VND` according to ISO 4217 codes supported by the JDK.
- `java.util.Locale`: identifies **language and region conventions**, such as `en-US`, `de-DE`, `vi-VN`, passed to the formatter to choose how to display values.
- `java.math.BigDecimal`: represents exact **decimal numeric values**, suitable for monetary calculations with clear rules.
- `java.text.NumberFormat` and `java.text.DecimalFormat`: produce **display strings** according to the locale and currency unit configuration.

A design rule: **a transaction's currency is business data; a locale is the reader's presentation preference**. Do not use the locale to guess an invoice's currency when the system already knows the invoice is in USD, EUR, or VND.

## 2. Distinguishing Currency, Locale, and Amount

| Concept | Question answered | Example | Commonly used API |
| --- | --- | --- | --- |
| Amount (`amount`) | How much money is there? | `1234.50` | `BigDecimal` |
| Unit (`currency`) | What currency is 1234.50 denominated in? | `USD` | `Currency` |
| Presentation convention (`locale`) | How does the reader expect numbers and symbols to appear? | `Locale.GERMANY` | `Locale` |
| Formatter | How to turn amount + currency into a string for a locale? | `1.234,50 $` | `NumberFormat`/`DecimalFormat` |
| Exchange rate | At what price to convert one currency unit to another? | USD/EUR rate at a specific time | Business service/data, **not** `NumberFormat` |

**Mental model examples:**

1. `amount = 1234.50`, `currency = USD`, `locale = en-US` → formatted in US style.
2. Keep **amount and currency**, change `locale = de-DE` → formatted in German style.
3. Keep amount and locale, but change `currency = EUR` → **changes the meaning of the monetary amount**, no longer the same unit.
4. To get the EUR value equivalent to 1234.50 USD, you must perform a **conversion using an exchange rate** first, then format the new amount.

For storage and APIs, a monetary amount normally needs at least two fields: **amount** and **currency code**. A display string is output for reading, not a canonical data source for calculation.

## 3. java.util.Currency: currency codes and properties

### 3.1. Obtaining a Currency object

Create a currency unit from a supported currency code:

```java
import java.util.Currency;

Currency usd = Currency.getInstance("USD");
Currency eur = Currency.getInstance("EUR");
Currency vnd = Currency.getInstance("VND");
Currency jpy = Currency.getInstance("JPY");
```

The code must have the proper format and be supported by the JDK's currency dataset. `getInstance(String)` can throw `IllegalArgumentException` if the code is invalid/unsupported. Do not automatically treat any arbitrary three-letter string as an accepted currency code in your product.

`Currency` also provides:

```java
usd.getCurrencyCode();           // "USD"
usd.getNumericCode();            // ISO 4217 numeric code provided by the JDK
usd.getDefaultFractionDigits();  // Usually 2 for USD
usd.getSymbol(Locale.US);        // Appropriate symbol for the locale
usd.getDisplayName(Locale.US);   // Display name according to the locale
```

Symbols and display names can depend on the locale/provider data of the JDK version. A symbol like `$` **is not enough to identify a currency unit**, because many units may use a similar symbol. For data exchange and bookkeeping, prefer specific codes such as `USD`/`CAD`/`AUD` rather than trying to guess from a symbol.

### 3.2. What does Currency.getInstance(Locale) mean?

`Currency.getInstance(locale)` attempts to find the currency **associated with the country/region in the locale**, according to JDK currency data. For example:

```java
Currency regional = Currency.getInstance(Locale.GERMANY);
System.out.println(regional.getCurrencyCode()); // EUR
```

This **does not prove** that every invoice displayed in Germany must be in EUR. A German customer can completely legitimately pay an invoice in USD. `Locale.GERMANY` only tells the formatter how to display values and can identify the **regional default currency** in an appropriate context.

Do not infer currency solely from a language like `"en"` or `"vi"`: a single language is spoken in many countries. `Currency.getInstance(Locale)` requires appropriate region information; a locale without a country can cause `IllegalArgumentException`. Some regions without a current currency can return `null`. Therefore, if an application **needs a transaction currency**, store/receive the currency explicitly instead of relying on the UI language.

### 3.3. Default fraction digits

`Currency.getDefaultFractionDigits()` returns the default number of decimal digits according to the JDK's ISO 4217 data:

| Currency | Common value | Meaning |
| --- | ---: | --- |
| `USD` | 2 | Usually represents cents with two digits |
| `EUR` | 2 | Usually represents cents with two digits |
| `JPY` | 0 | Yen normally has no decimal fractional part |
| `VND` | 0 | Vietnamese dong typically has zero fraction digits under this convention |

Some special codes can return `-1` to indicate that no default fraction digit count applies. **Do not assume every currency always has 2 digits.**

However, this is a **default property**, not the final rounding law for all business cases. For example: internal unit prices may need more digits than the settlement amount; accounting systems may maintain a separate scale; tax regulations or payment methods may require rounding at a different step. Define those rules explicitly.

## 4. java.util.Locale determines display conventions

`Locale` affects aspects such as:

- **Decimal separator**: many English formats use `.`, while many German formats use `,`.
- **Grouping separator**: may be a comma, period, space, non-breaking space, or another character depending on the locale.
- **Symbol placement and formatting**: before or after the number, potentially with added whitespace.
- **Currency symbol/code**: the same USD may display as `$`, `US$`, or another name/code depending on context and locale data.
- **Negative number presentation** and accounting conventions if the formatter is configured accordingly.
- **Numbering system** and other localized data in locales with appropriate extensions.

These choices **do not alter the arithmetic value**. If you format the same `BigDecimal("1234.50")`, the underlying amount remains `1234.50` even though the screen shows different punctuation.

`Locale.forLanguageTag("de-DE")` specifies German conventions; `Locale.forLanguageTag("vi-VN")` specifies the Vietnamese context in Vietnam. Do not treat `Locale` as a "currency unit". Nor should you change `Locale.setDefault(...)` JVM-wide to format individual web server requests: the default is shared state, creating risks across concurrent users. Pass `Locale` explicitly to the formatter.

## 5. NumberFormat.getCurrencyInstance and setCurrency

### 5.1. Creating a formatter by locale

`NumberFormat.getCurrencyInstance(locale)` creates a currency formatter with the default presentation conventions of the locale. For example:

```java
NumberFormat us = NumberFormat.getCurrencyInstance(Locale.US);
NumberFormat germany = NumberFormat.getCurrencyInstance(Locale.GERMANY);
```

Ordinarily, a formatter created for `Locale.US` uses USD by default, and a formatter created for `Locale.GERMANY` uses EUR by default. However, the unit initially chosen by the formatter is merely a **locale-associated default**, not the mandatory currency of the data being printed.

### 5.2. The transaction's unit must be set explicitly

If the same USD transaction is displayed to two users:

```java
Currency transactionCurrency = Currency.getInstance("USD");
BigDecimal amount = new BigDecimal("1234.50");

NumberFormat usFormat =
        NumberFormat.getCurrencyInstance(Locale.US);
NumberFormat deFormat =
        NumberFormat.getCurrencyInstance(Locale.GERMANY);

usFormat.setCurrency(transactionCurrency);
deFormat.setCurrency(transactionCurrency);

String forAmericanUser = usFormat.format(amount);
String forGermanUser = deFormat.format(amount);
```

The two strings can differ significantly in separators, symbol position, and whitespace. **Both still format 1234.50 USD**; there is no exchange-rate multiplication or division in `setCurrency` or `format`.

A more explicit way to write this is:

```java
String formatMoney(BigDecimal amount, Currency currency, Locale locale) {
    NumberFormat fmt = NumberFormat.getCurrencyInstance(locale);
    fmt.setCurrency(currency);
    return fmt.format(amount);
}
```

This is a **method snippet** (not a standalone Java file), requiring imports `java.math.BigDecimal`, `java.util.Currency`, `java.util.Locale`, `java.text.NumberFormat`. A complete program appears later.

### 5.3. Important pitfall: setCurrency does not automatically change fraction digits

`setCurrency(currency)` on `NumberFormat` changes the currency used by the formatter; by the API specification, it **does not automatically update** `getMinimumFractionDigits()` and `getMaximumFractionDigits()`. This goes against the intuition that "switching to JPY always drops fractional digits automatically".

Example:

```java
NumberFormat fmt =
        NumberFormat.getCurrencyInstance(Locale.US);
int before = fmt.getMaximumFractionDigits();

fmt.setCurrency(Currency.getInstance("JPY"));

int after = fmt.getMaximumFractionDigits();
// Per the setCurrency contract: before == after.
```

Because a standard `Locale.US` formatter is already configured with two digits after the decimal point, switching the currency to JPY without reconfiguring can produce a JPY string with **two fractional digits**, whereas `Currency.getInstance("JPY").getDefaultFractionDigits()` is 0.

If your product's presentation policy is to use the currency's default digit count, you must update it separately:

```java
int digits = currency.getDefaultFractionDigits();
if (digits >= 0) {
    fmt.setMinimumFractionDigits(digits);
    fmt.setMaximumFractionDigits(digits);
}
```

This is a snippet with already-initialized `currency`/`fmt` variables. This rule is **a presentation choice**, not a replacement for payment/accounting policy. In particular, never set `-1` as fraction digits; you must handle currencies that have no default.

### 5.4. Currency.getSymbol and currency patterns

`Currency.getSymbol(locale)` returns a symbol for a display context. `NumberFormat.getCurrencyInstance(locale)` chooses symbol placement, spacing, grouping, and negative sign formatting as well — none of which can be faithfully reproduced by string concatenation:

```java
currency.getSymbol(locale) + amount.toString()
```

This concatenation can produce the wrong decimal separator, wrong symbol placement, and missing whitespace. With `DecimalFormat`, the `¤` character in a pattern represents the currency; `¤¤` typically requests the currency code instead of the symbol, but custom patterns must be applied together with appropriate `DecimalFormatSymbols`. You should not apply one locale's fixed pattern to all other languages.

## 6. Standalone Java 17+ example: same USD, two locales

Create a UTF-8 file named **`CurrencyAndLocaleDemo.java`**:

```java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.util.Currency;
import java.util.Locale;

public class CurrencyAndLocaleDemo {
    public static void main(String[] args) {
        Currency usd = Currency.getInstance("USD");
        Currency jpy = Currency.getInstance("JPY");
        BigDecimal amount = new BigDecimal("1234.50");

        NumberFormat us = NumberFormat.getCurrencyInstance(Locale.US);
        NumberFormat german =
                NumberFormat.getCurrencyInstance(Locale.GERMANY);

        us.setCurrency(usd);
        german.setCurrency(usd);

        System.out.println("Region currency: "
                + Currency.getInstance(Locale.GERMANY).getCurrencyCode());
        System.out.println("Transaction currency: "
                + usd.getCurrencyCode());
        System.out.println("US formatter currency: "
                + us.getCurrency().getCurrencyCode());
        System.out.println("DE formatter currency: "
                + german.getCurrency().getCurrencyCode());

        String usText = us.format(amount);
        String germanText = german.format(amount);
        System.out.println("Different presentation: "
                + !usText.equals(germanText));
        System.out.println("Amount unchanged: " + amount.toPlainString());

        System.out.println("USD fraction digits: "
                + usd.getDefaultFractionDigits());
        System.out.println("JPY fraction digits: "
                + jpy.getDefaultFractionDigits());

        NumberFormat usJpy =
                NumberFormat.getCurrencyInstance(Locale.US);
        int before = usJpy.getMaximumFractionDigits();
        usJpy.setCurrency(jpy);

        System.out.println("JPY configured: "
                + usJpy.getCurrency().getCurrencyCode());
        System.out.println("Maximum fraction digits unchanged: "
                + (before == usJpy.getMaximumFractionDigits()));
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac -encoding UTF-8 CurrencyAndLocaleDemo.java
java CurrencyAndLocaleDemo
```

Output on a JDK with modern currency/locale data:

```text
Region currency: EUR
Transaction currency: USD
US formatter currency: USD
DE formatter currency: USD
Different presentation: true
Amount unchanged: 1234.50
USD fraction digits: 2
JPY fraction digits: 0
JPY configured: JPY
Maximum fraction digits unchanged: true
```

Explanation:

1. The currency obtained from **the Germany region** is EUR, while the transaction data is explicitly chosen as USD.
2. Both formatters are configured with `USD`, even though one formats for `Locale.US` and the other for `Locale.GERMANY`.
3. `Different presentation: true` verifies a difference in display output **without hardcoding** punctuation, spacing, or symbol placement that may vary by JDK locale data.
4. `amount.toPlainString()` remains `1234.50`; formatting does not convert currency or modify the `BigDecimal`.
5. USD defaults to two fraction digits, and JPY defaults to zero fraction digits. After `setCurrency(jpy)`, `getMaximumFractionDigits` is still not automatically changed.

If you need to inspect the exact currency strings for both locales on your machine, print `usText` and `germanText` as well. The strings may contain **non-breaking spaces** or currency symbols supplied by CLDR/JDK; therefore, you should not treat display examples in documentation as a fixed contract across all environment versions.

## 7. Storing money with BigDecimal and Currency

### 7.1. Do not use double as the source of truth for money

`double` values are binary approximations. In multi-step monetary calculations — especially addition, proportional allocation, tax, and interest — using `double` can produce results that do not match decimal expectations. A simple foundational data type:

```java
import java.math.BigDecimal;
import java.util.Currency;

public record Money(BigDecimal amount, Currency currency) {
    public Money {
        if (amount == null || currency == null) {
            throw new IllegalArgumentException(
                    "Amount and currency are required");
        }
    }
}
```

This is **a standalone Java file named `Money.java`** if placed in a project; records are supported since Java 16, so it runs on Java 17+. You should not turn every monetary amount into a formatted string right at the data layer. The record above illustrates storing the exact two components, and **does not yet implement all business rules** such as non-negativity, valid scale, overflow checks, or rounding.

Usage example:

```java
Money bill = new Money(
        new BigDecimal("1234.50"),
        Currency.getInstance("USD")
);
```

When sending over JSON/APIs, pass the currency code and exact decimal amount (or a canonical decimal string depending on the contract), not a string with `$`/grouping separators added. The receiving side must revalidate both the currency code and amount.

### 7.2. Adding different currencies must be prevented

Two amounts `100 USD` and `100 EUR` cannot simply be added as `100 + 100 = 200` and treated as a single valid monetary amount. Even if both have two fraction digits, **their units differ**. An addition function must verify matching currencies, or require an exchange-rate conversion process beforehand:

```java
static Money add(Money a, Money b) {
    if (!a.currency().equals(b.currency())) {
        throw new IllegalArgumentException("Currency mismatch");
    }
    return new Money(
            a.amount().add(b.amount()),
            a.currency()
    );
}
```

This is a **snippet** inside a class with access to the `Money` record above. Checking the unit is the essential part, because a formatter can certainly print the same style for two values of different units without making them equivalent.

### 7.3. Formatting never determines exchange rates

`fmt.setCurrency(Currency.getInstance("EUR"))` only tells the formatter to use EUR when generating text. It **does not** convert `1234.50 USD` into an equivalent EUR amount. Doing so requires:

- A reliable exchange-rate source and the currency pair in the right direction.
- The effective timestamp of the exchange rate.
- Rounding/scale rules decided by the business.
- Handling fees, spread, taxes, and recording differences if applicable.

Only after computing the new EUR value do you format it with the EUR currency and the reader's locale. The `Currency`/`NumberFormat` APIs do not provide exchange rates.

## 8. Fraction digits and RoundingMode: business logic first, presentation second

Suppose a JPY order has an intermediate calculated value of `1234.50`. A formatter using JPY's default fraction digits may display a rounded integer; that **does not automatically prove** the system is authorized to charge/pay that exact integer. The final monetary calculation step must follow product/payment-method policy, and only then be displayed.

For `BigDecimal`:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal exact = new BigDecimal("1234.50");
BigDecimal rounded = exact.setScale(0, RoundingMode.HALF_UP);

System.out.println(rounded.toPlainString()); // 1235
```

This is an **in-method snippet**, not a complete Java program. `setScale(...)` creates a new value; `exact` is not mutated because `BigDecimal` is immutable. If the transaction currency is JPY, choosing `HALF_UP` is merely a policy example, not a mandatory international rule.

For presentation after calculation:

```java
NumberFormat formatter =
        NumberFormat.getCurrencyInstance(locale);
formatter.setCurrency(currency);
formatter.setRoundingMode(RoundingMode.HALF_UP);

int digits = currency.getDefaultFractionDigits();
if (digits >= 0) {
    formatter.setMinimumFractionDigits(digits);
    formatter.setMaximumFractionDigits(digits);
}

String label = formatter.format(amount);
```

This snippet assumes variables `locale` of type `Locale`, `currency` of type `Currency`, and `amount` of type `BigDecimal`; imports `java.text.NumberFormat` and `java.math.RoundingMode` are required. Setting the formatter's rounding mode only controls **the display string**; if the business needs to round the recorded amount, do so in the domain layer using `BigDecimal` and a tested policy.

**Do not assume "2 fraction digits" means every currency has cents.** Aside from USD/EUR, many currencies have 0 or a different number of digits; meanwhile, some intermediate values for pricing/unit rates require a larger scale than the default. Keep currency rules and calculation rules separate.

## 9. Parsing: you may read the number, but not necessarily know the currency

Formatting goes **value → string**, whereas parsing goes **string → value**. With user input, locale-aware parsing requires knowing the decimal/grouping separators the UI uses. `NumberFormat.parse(...)` can return `Long` or `Double` and **does not carry a Currency** in the returned numeric value.

For decimal numbers needing precision, on a formatter that is actually a `DecimalFormat` you can enable:

```java
DecimalFormat parser = new DecimalFormat(
        "#,##0.00",
        DecimalFormatSymbols.getInstance(Locale.US)
);
parser.setParseBigDecimal(true);
```

Then parse the numeric text with `ParsePosition` and verify the entire string was consumed; the result is typically a `BigDecimal` for finite numbers. Imports `java.text.DecimalFormat`, `DecimalFormatSymbols`, and `java.util.Locale` are required. If the input is a **currency string with a symbol**, you must have a suitable pattern/parser; do not blindly strip all non-digit characters, as doing so loses negative signs, separators, and **fails to validate the currency type**.

**Unit constraint:** Even if the parser reads the string `"1,234.50"` into `BigDecimal("1234.50")`, the application still needs to know whether it is USD, EUR, or VND from a separate currency field or product selection. The `$` sign may be insufficient to distinguish USD/CAD/AUD; do not treat a successful parse as proof that the currency was validated.

**Security and data constraints:** Limit input length, magnitude, and number of decimal digits; check that the entire string was parsed, guard against unexpected Unicode characters; and avoid accepting an invalid monetary value just because the formatter is lenient enough to read part of the string.

## 10. Displaying correctly when user and transaction have different regions

In practice:

**Scenario A: buyer in Germany, USD invoice.** Store amount `1234.50` and currency `USD`; use `Locale.GERMANY` in the formatter. Do not replace the currency with EUR just because the buyer uses `de-DE`.

**Scenario B: Vietnamese user views prices in JPY.** Store currency `JPY`; use `Locale.forLanguageTag("vi-VN")` if you want messaging and presentation familiar in Vietnam. When applying fraction digits for JPY, the display policy may have no fractional part; never convert JPY to VND automatically.

**Scenario C: two reports with the same figures, two locales.** Keep the `BigDecimal` and `Currency` values from the same data source; format separately for each reader. Do not re-parse a string formatted in locale A and reformat it to locale B to produce report B, because parsing can lose precision, round, or misread signs.

**Scenario D: needing to display the code instead of the symbol.** A financial interface might choose to display `USD 1,234.50` or `1.234,50 USD` by its own rules to avoid an ambiguous `$` sign. That is still a **presentation** decision. The currency code must be kept in the model, not inferred from display labels.

**Scenario E: exchange rate changes.** If USD has already been converted to EUR, the new record must store both the EUR currency and the EUR amount as of the exchange rate timestamp; a different rendering on screen must not be treated as a conversion operation.

## 11. Common mistakes

| Mistake | Consequence | Solution |
| --- | --- | --- |
| Using `Currency.getInstance(userLocale)` as the transaction currency | A USD transaction can be mislabeled as EUR/VND based on the reader | Obtain the currency from the order, contract, or product |
| Storing only `"1.234,50 $"` instead of amount and currency | Hard to distinguish symbols, hard to parse, loses canonical data | Store `BigDecimal` and ISO currency code |
| Treating `setCurrency(EUR)` as converting USD to EUR | Changes the label without applying an exchange rate | Perform business conversion first |
| Using `NumberFormat.getCurrencyInstance(locale)` without `setCurrency` for cross-region data | Uses the region's default currency, wrong unit | `setCurrency(transactionCurrency)` |
| Believing `setCurrency(JPY)` automatically sets 0 fraction digits | Can still print 2 digits from the original formatter | Configure minimum/maximum fraction digits explicitly |
| Assuming every currency has two fraction digits | Wrong for JPY/VND and many other codes | Check `getDefaultFractionDigits()` and custom policies |
| Concatenating `currency.getSymbol(locale) + amount` | Wrong punctuation, placement, and spacing | Use a currency-aware formatter |
| Reading a `$` sign and concluding it is definitely USD | Symbol is shared across many currencies | Store/transmit explicit `USD`, `CAD`, `AUD` codes |
| Using `double` to calculate/hold monetary amounts | Binary rounding error, inaccuracies across repeated additions/multiplications | Use `BigDecimal` with explicit rounding |
| Using display strings to recalculate monetary amounts | Parsing depends on locale and may already be rounded | Keep exact domain values and format at the boundary |
| Changing `Locale.setDefault` per request | Global side effects on other requests | Pass locale explicitly |
| Sharing a mutable `NumberFormat` across threads while repeatedly changing currency | Risk of mixed results; formatter is not guaranteed thread-safe | Create separate formatters or synchronize access |
| Comparing outputs with whitespace/symbols as fixed ASCII | Easily fails when CLDR/JDK data changes | Test structure/semantics, pin provider, or update golden tests |

Some currencies change codes, circulation regions, or properties over time. `Currency` data depends on the JDK version/configuration; for financial systems requiring long-term storage, **record the original currency code and the rules effective for the transaction**, rather than treating the current JDK defaults as historical proof.

## 12. Testing checklist

| Case | Expected outcome to verify |
| --- | --- |
| Same amount + USD, presented in `en-US` and `de-DE` | Still USD, only the display string differs |
| Same locale, changing currency from USD to EUR | Formatter uses EUR, does **not** convert the number automatically |
| `Currency.getInstance(Locale.GERMANY)` | Returns Germany's regional currency, does not represent an arbitrary transaction's default |
| `getDefaultFractionDigits` of USD/JPY/VND | Do not assume all are 2 |
| `setCurrency(JPY)` on a US-based formatter | Min/max fraction digits do not change unless reconfigured |
| Amount `1234.50` as `BigDecimal` | No precision loss from a `double` conversion path |
| Negative values and very large numbers | Sign, grouping, and rounding are valid |
| Locales with different symbol placement | Spacing, currency code, and sign display properly |
| Invalid currency code | Rejected/handled with an appropriate message |
| Input containing a `$` symbol | Currency is not inferred from an ambiguous symbol |
| Adding `Money` of different currencies | Rejected or requires business conversion |
| Multi-threaded requests with different locales | No formatter cross-contamination or JVM default mutation |
| Upgrading JDK/locale data | UI golden tests are intentionally re-evaluated |

Beyond unit tests, you should test on actual UIs because non-breaking spaces, text direction, symbol width, and number alignment can differ by font, platform, and locale. Having the right monetary value in an unreadable layout is still a product defect.

## 13. Self-check questions

**Question 1.** The invoice is `100 USD`, and the reader uses `Locale.GERMANY`. Does Java automatically convert it to EUR?

**Answer:** No. `Locale.GERMANY` determines presentation; you must pass `Currency.getInstance("USD")` to the formatter. Getting EUR requires a separate business exchange-rate conversion.

**Question 2.** What is `Currency.getInstance("JPY").getDefaultFractionDigits()` usually? Does that guarantee the active formatter will automatically drop fractional digits after `setCurrency(JPY)`?

**Answer:** The default value is 0 in current data, but `setCurrency` does not automatically adjust the formatter's minimum/maximum fraction digits properties. You must configure them separately according to policy.

**Question 3.** Can `$1,234.50` and `1.234,50 $` represent the same monetary amount?

**Answer:** Yes, if both have amount `1234.50` and currency USD. The difference comes solely from presentation conventions. The `$` sign alone is not enough to conclude a value is definitely USD.

**Question 4.** Why is storing `BigDecimal` with `Currency` better than storing a formatted currency string?

**Answer:** It preserves exact decimal numbers and an unambiguous unit, allowing accurate calculations/currency conversions and formatting across many locales without reverse-parsing presentation strings.

**Question 5.** If you want to display `1234.50 USD` to Vietnamese and English users, what data must stay fixed?

**Answer:** Keep amount `1234.50` and currency `USD` fixed; vary the formatter's locale per user. Only presentation elements change.

**Question 6.** If a user selects the `EUR` currency but the original order stores USD, can you simply call `formatter.setCurrency(EUR)` and consider the conversion complete?

**Answer:** No. Changing the currency on the formatter only changes formatting configuration. You must calculate the EUR amount using a valid exchange rate and transaction rules, then format the result.

## 14. Key takeaways and references

- **Currency is the monetary unit; Locale is the presentation convention.** The two concepts are independent and must be kept in their proper roles.
- `Currency.getInstance("USD")` identifies a specific unit; `Currency.getInstance(locale)` only retrieves the region-associated currency per JDK data and does not confirm an order's real currency.
- `NumberFormat.getCurrencyInstance(locale)` creates display rules; `setCurrency(currency)` sets the currency unit for the label. **Neither API performs exchange-rate conversion**.
- `setCurrency` does not automatically update fraction-digit limits. Check `getDefaultFractionDigits` and apply your application's display/calculation policy.
- Store amounts as `BigDecimal` and currencies as explicit codes; do not use `double` as the source of truth or formatted strings for calculations.
- Format according to locale at the UI layer, test encoding/symbols/whitespace, and use separate formatters per execution flow.

**Official documentation:**

- [Java SE 21 — Currency](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Currency.html)
- [Java SE 21 — NumberFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/NumberFormat.html)
- [Java SE 21 — DecimalFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/DecimalFormat.html)
- [Java SE 21 — BigDecimal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html)
