# Why Changing a Currency Symbol or Code Does Not Convert Value in Java

## 1. The problem: the same number, two different currencies

Suppose an application has an invoice for **100.00 USD**. When switching the display language or region, the UI may use a different notation—for example, changing the symbol placement, digit grouping, or decimal separator. However, **changing the notation does not turn 100 USD into 100 EUR**.

A dangerous bug is taking a currency formatter currently displaying USD, calling `setCurrency(EUR)`, seeing the “€” character appear, and concluding that the system has converted the amount. The underlying numeric value is still 100; no exchange rate was fetched and no multiplication or division was performed.

Three concepts must be kept independent:

1. **Amount:** a computable value, usually represented with `BigDecimal`, such as `100.00`.
2. **Currency:** the unit of money that the value represents, such as `USD` or `EUR`, usually represented with `java.util.Currency` and an ISO 4217 code.
3. **Presentation:** how the user wants to view the monetary amount, such as symbol form (`$`, `US$`, `€`) or code (`USD`) depending on the locale and formatter.

**Foreign-exchange conversion** is a separate business operation: it needs the source currency, target currency, correctly oriented exchange rate, quote timestamp, rounding policy, and possibly fees. `Currency`, `Locale`, and `NumberFormat` **do not provide exchange rates**.

### Objectives

After this lesson, you can explain why `NumberFormat.setCurrency` and `Currency.getSymbol` only affect presentation metadata; model a monetary amount with both amount and currency; perform a well-specified conversion using `BigDecimal`; handle fraction digits, rounding, locale, and API contracts; and avoid confusing a formatted string with an actual monetary amount.

## 2. Changing the label does not change the quantity

Imagine a bottle label that reads **1 liter**. If you replace the word “liter” with “gallon” without **changing the number 1**, you have created a wrong label, not converted the unit. Money works the same way:

```text
ORIGINAL VALUE                  OPERATION                   RESULT
100.00 USD
    |
    +-- Change display Locale ----------------------> "100,00 ..."
    |                                                (formatting changes)
    |
    +-- Change symbol / Currency in formatter ------> "€100.00"
    |                                                (number stays 100.00)
    |
    +-- Convert at rate 0.9150 EUR / USD -----------> 91.50 EUR
                                                     (recalculated value)
```

The strings in the diagram only illustrate **meaning**; they do not define the exact spacing or symbols for every locale and JDK version.

A `Currency` object describes **a currency unit**, not a “monetary amount with value.” For example, `Currency.getInstance("USD")` knows the code `USD`, locale-specific names/symbols, and the currency's default number of fraction digits; it does not know “how many EUR 100 USD is worth today.”

Similarly, `Locale.FRANCE` may cause a default currency formatter to choose EUR and French formatting conventions; however, that does not imply a USD amount in the system has been converted to EUR. **The viewer's locale is not the transaction's currency.**

## 3. Distinguishing commonly misunderstood Java APIs

| API / Operation | What does it do? | Does it convert the monetary amount? |
| --- | --- | --- |
| `Currency.getInstance("USD")` | Retrieves the object describing the USD currency unit | **No** |
| `currency.getCurrencyCode()` | Retrieves the ISO 4217 code, e.g. `USD` | **No** |
| `currency.getSymbol(locale)` | Retrieves the currency symbol appropriate for the locale | **No** |
| `currency.getDisplayName(locale)` | Retrieves the currency name in the locale's language | **No** |
| `Currency.getInstance(locale)` | Infers the default currency associated with the territory (when available) | **No** |
| `NumberFormat.getCurrencyInstance(locale)` | Creates a currency formatter using locale conventions | **No** |
| `numberFormat.setCurrency(otherCurrency)` | Replaces the Currency used by the formatter | **No** |
| `numberFormat.format(amount)` | Converts a number into a display **string** | **No** |
| `amount.multiply(rate)` | Performs arithmetic multiplication | **Can be a conversion step**, if the rate is oriented properly and has a business policy |

### 3.1. `Currency` is unit metadata

`java.util.Currency` is the class that describes a currency. Key methods to remember:

```java
import java.util.Currency;
import java.util.Locale;

Currency usd = Currency.getInstance("USD");
Currency eur = Currency.getInstance("EUR");

System.out.println(usd.getCurrencyCode());       // USD
System.out.println(eur.getCurrencyCode());       // EUR
System.out.println(usd.getDefaultFractionDigits()); // 2
System.out.println(usd.getSymbol(Locale.US));    // Symbol for Locale.US
```

This is an **illustrative snippet** inside a method; the comments only explain the values. `getDefaultFractionDigits()` indicates the standard number of decimal places for the currency (for example, USD and EUR are typically 2, JPY is 0). It does not tell you the exchange rate or how many units of the source currency are needed to buy one unit of the target currency. For certain special codes, the result can be `-1`, so you should check it before using it to set a scale.

A symbol is not a unique identifier: the `$` sign is used by many currencies. A locale may return a distinct symbol such as `US$` to disambiguate. Codes like `USD` or `CAD` are usually better suited for **storage/APIs**, whereas symbols are better suited for **display**.

### 3.2. `Locale` is not an exchange rate

`Locale.forLanguageTag("vi-VN")` describes the language/region for formatting and message translation. A user in Vietnam can still view a USD or JPY transaction; an English-speaking user can pay in VND. Time zone, address, country of residence, and settlement currency also must not be inferred solely from the locale.

You can use `Currency.getInstance(Locale.US)` to obtain the default currency unit associated with the United States territory; that **does not turn all transactions viewed with `Locale.US` into USD**. For a locale without a country or a territory without a matching currency unit, retrieving a currency from a locale must handle exceptions or missing-currency results rather than assuming it always succeeds.

### 3.3. `NumberFormat.setCurrency` performs no math

With `NumberFormat.getCurrencyInstance(locale)`, `setCurrency(currency)` configures the formatter's currency for generating strings. It **takes no exchange rate**, **does not know the source currency of the number**, and **does not modify the `BigDecimal` variable** being formatted.

One subtle detail in Java: `NumberFormat.setCurrency` **does not automatically adjust** the formatter's `minimumFractionDigits` and `maximumFractionDigits`. When switching from a currency that typically has 2 decimal places to one that typically has no minor units, such as JPY, you must explicitly configure the appropriate precision or create a formatter with the right policy rather than relying on `setCurrency` to “fix everything.”

## 4. Java 17 example: changing the symbol keeps the original number intact

File `CurrencyLabelDemo.java`:

```java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.util.Currency;
import java.util.Locale;

public class CurrencyLabelDemo {
    record Money(BigDecimal amount, Currency currency) {}

    public static void main(String[] args) {
        Money original = new Money(
                new BigDecimal("100.00"),
                Currency.getInstance("USD"));

        NumberFormat formatter =
                NumberFormat.getCurrencyInstance(Locale.US);

        formatter.setCurrency(original.currency());
        String asUsd = formatter.format(original.amount());

        // Only changes the formatter's Currency; does NOT change Money.
        formatter.setCurrency(Currency.getInstance("EUR"));
        String asEurLabel = formatter.format(original.amount());

        System.out.println("amount=" +
                original.amount().toPlainString());
        System.out.println("moneyCurrency=" +
                original.currency().getCurrencyCode());
        System.out.println("formatterCurrency=" +
                formatter.getCurrency().getCurrencyCode());
        System.out.println("sameAmount=" +
                original.amount().equals(new BigDecimal("100.00")));

        System.out.println("before=" + asUsd);
        System.out.println("after=" + asEurLabel);
    }
}
```

Compile/run with JDK 17 or later:

```bash
javac -encoding UTF-8 CurrencyLabelDemo.java
java CurrencyLabelDemo
```

**The first four lines have exact output:**

```text
amount=100.00
moneyCurrency=USD
formatterCurrency=EUR
sameAmount=true
```

With standard locale data for `Locale.US`, the next two lines typically display something like:

```text
before=$100.00
after=€100.00
```

Punctuation, whitespace, and displayed symbols come from locale data and may differ across providers, vendors, and JDK versions; these two lines are a typical example, **not a string contract for every environment**.

This is precisely the **dangerous** situation: the `after` line displays the EUR symbol next to the number `100.00`, yet the `original` object still has unit **USD**. If this string is shown to a user as “100 EUR” without conversion, the application has attached a **wrong label to a value**. `setCurrency` neither turns `100 USD` into `100 EUR` nor creates a new `Money` object with a valid currency.

Practical rule: **Do not change the currency on a formatter to simulate a “Convert to EUR” feature.** The formatter must receive the currency of the *amount after business calculation*.

## 5. What components does a real conversion require?

Converting from USD to EUR can be expressed by the formula:

\[
\text{amount}_{EUR} = \text{amount}_{USD} \times
    \left(\frac{\text{EUR}}{\text{USD}}\right)
\]

Here, the exchange rate must be defined **in the right direction**. For example, a rate of `0.9150 EUR per 1 USD` means each 1 USD converts to 0.9150 EUR (before fees and rounding). An amount of 100.00 USD becomes:

\[
100.00 \times 0.9150 = 91.500000
\]

If the rounding policy for EUR is 2 decimal places, the stored/settled result in this example is **91.50 EUR**.

**The rate 0.9150 is strictly hypothetical data for learning purposes**, not a verified market rate, live rate, or trading advice. In production, quotes must come from an approved source, carry a timestamp, and have their validity verified.

A complete conversion typically requires:

| Component | Example | Meaning |
| --- | --- | --- |
| Source amount | `100.00` | Value to convert |
| Source currency (base) | `USD` | Unit of the source amount |
| Target currency (quote/counter) | `EUR` | Unit of the result |
| Directed exchange rate | `0.9150 EUR/USD` | Number of EUR per USD |
| Quote timestamp | `2026-10-28T00:00:00Z` | When the quote is valid |
| Precision and rounding | `scale=2, HALF_EVEN` | Rounding rule for the target currency in the example |
| Fees, spread, taxes (if any) | Per contract | Must have explicit rules; not computed by the formatter |

If the rate is defined in the reverse direction, such as `USD per EUR`, you must not multiply blindly: you need to invert it with an appropriate division and define precision/rounding for that operation. Even the mathematical inverse of a rate may **not be the actual trading rate** because buy/sell rates involve spreads and fees.

## 6. Java 17 example: computing a new amount with BigDecimal

The following `FxConversionDemo.java` file produces **a new result** instead of merely swapping a label. It uses a hypothetical rate, validates the currency pair, multiplies with `BigDecimal`, and specifies rounding for the target amount.

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Instant;
import java.util.Currency;

public class FxConversionDemo {
    record Money(BigDecimal amount, Currency currency) {}

    record Quote(
            Currency baseCurrency,
            Currency counterCurrency,
            BigDecimal counterPerBase,
            Instant asOf
    ) {}

    static Money convert(
            Money source, Quote quote, Currency target) {

        if (!source.currency().equals(quote.baseCurrency())
                || !target.equals(quote.counterCurrency())) {
            throw new IllegalArgumentException("Wrong FX pair");
        }

        BigDecimal rawTarget =
                source.amount().multiply(quote.counterPerBase());

        int digits = target.getDefaultFractionDigits();
        if (digits < 0) {
            throw new IllegalArgumentException(
                    "Currency minor-unit policy required");
        }

        BigDecimal rounded =
                rawTarget.setScale(digits, RoundingMode.HALF_EVEN);

        return new Money(rounded, target);
    }

    public static void main(String[] args) {
        Currency usd = Currency.getInstance("USD");
        Currency eur = Currency.getInstance("EUR");

        Money source = new Money(new BigDecimal("100.00"), usd);

        // HYPOTHETICAL RATE for lesson purposes only.
        Quote quote = new Quote(
                usd,
                eur,
                new BigDecimal("0.9150"),
                Instant.parse("2026-10-28T00:00:00Z"));

        Money target = convert(source, quote, eur);

        System.out.println("source=" +
                source.amount().toPlainString() + " " +
                source.currency().getCurrencyCode());
        System.out.println("rate=" +
                quote.counterPerBase().toPlainString() +
                " EUR per USD");
        System.out.println("asOf=" + quote.asOf());
        System.out.println("target=" +
                target.amount().toPlainString() + " " +
                target.currency().getCurrencyCode());
        System.out.println("sourceUnchanged=" +
                source.amount().toPlainString() + " " +
                source.currency().getCurrencyCode());
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 FxConversionDemo.java
java FxConversionDemo
```

**Exact stdout with JDK 17, USD/EUR currencies, and the hypothetical data above:**

```text
source=100.00 USD
rate=0.9150 EUR per USD
asOf=2026-10-28T00:00:00Z
target=91.50 EUR
sourceUnchanged=100.00 USD
```

Key takeaways:

1. `Money` always has **both `BigDecimal` and `Currency`**—there is no state of “100, but unknown whether USD or EUR.”
2. `Quote` explicitly records base, counter, rate direction, and timestamp. Multiplying by 0.9150 makes sense because the rate is defined as **EUR per one USD**.
3. `convert` checks the currency pair to prevent accidentally applying a `EUR→USD` rate to a `USD→EUR` transaction.
4. The result is `new Money(91.50, EUR)`, distinct from `Money(100.00, USD)`. That is what **value conversion** actually is.
5. `BigDecimal` performs exact decimal arithmetic from strings; `setScale(2, HALF_EVEN)` is an example of a **business rounding policy**, not something `NumberFormat.format` decides on behalf of the business.
6. The program does not access the internet, does not use real market rates, and **does not include spread, fees, taxes, or expired quotes**.

In production, the scale policy may depend on payment method, legal regulations, currency unit, bank, and business rules; `Currency.getDefaultFractionDigits()` is a reference point for standard digits, not a settlement rule covering every case.

## 7. Why is BigDecimal more important than double for money?

Binary floating-point arithmetic with `double` cannot accurately represent many decimal numbers such as 0.1 or 0.2. For currency conversions, fee accumulation, transaction totals, and policy-based rounding, representation errors can alter results.

**Prefer:**

```java
BigDecimal amount = new BigDecimal("100.00");
BigDecimal rate = new BigDecimal("0.9150");
BigDecimal result = amount.multiply(rate);
```

Avoid constructing `new BigDecimal(0.1)` when you want the exact decimal value 0.1, because this constructor takes the exact binary approximation of `double`. If the value comes from a well-specified decimal string or a DECIMAL column in a database, preserve the decimal representation from the start.

`BigDecimal` also involves scale considerations:

- `new BigDecimal("1.0")` and `new BigDecimal("1.00")` have the same numeric value, but different scales.
- `equals` checks both value and scale, whereas `compareTo` compares numeric value.
- When dividing `BigDecimal` to invert a rate, you may encounter non-terminating decimal expansions. Pass an appropriate `MathContext` or scale/`RoundingMode`.
- A rule that rounds **after conversion** differs from **rounding after each fee step**; this must be specified explicitly to avoid discrepancies.

`NumberFormat` may round the **display string** without modifying the original `BigDecimal`. Never use formatted strings or re-parsed text as the source of truth for balances or transactions.

## 8. Fraction digits: changing currency does not reconfigure the whole formatter

Each currency has a different standard number of decimal places. For example:

| Currency | Typical `getDefaultFractionDigits()` | Display example |
| --- | ---: | --- |
| `USD` | 2 | `100.00` |
| `EUR` | 2 | `100.00` |
| `JPY` | 0 | `100` |
| `KWD` | 3 | `100.000` |

The table shows **default fraction digits of the currency**, not exchange rates or converted amounts. The right column shows raw numeric examples without currency symbols or locale punctuation rules.

A common mistake:

```java
NumberFormat f = NumberFormat.getCurrencyInstance(Locale.US);
f.setCurrency(Currency.getInstance("JPY"));
// Do not assume f has automatically set fraction digits = 0.
```

To format explicitly according to the target currency:

```java
import java.text.NumberFormat;
import java.util.Currency;
import java.util.Locale;

public class CurrencyDisplay {
    public static String show(
            java.math.BigDecimal amount,
            Currency currency,
            Locale displayLocale) {

        NumberFormat f =
                NumberFormat.getCurrencyInstance(displayLocale);

        f.setCurrency(currency);

        int digits = currency.getDefaultFractionDigits();
        if (digits >= 0) {
            f.setMinimumFractionDigits(digits);
            f.setMaximumFractionDigits(digits);
        }

        return f.format(amount);
    }
}
```

This is a **utility class compilable on Java 17** without `main`; it must be called from another program. The `digits >= 0` check avoids using the special value `-1` as an invalid scale. In financial systems, fraction digits and rounding policies should be defined with the business domain rather than merely copying defaults.

The `show` method formats the **amount and currency passed in**—it does not compute a target amount. To display a converted result, first call `convert` in the business layer, then call `show(target.amount(), target.currency(), locale)`. Conversely, displaying the source amount with the target currency **without converting first** produces false information.

### Why not guess currency from locale alone?

A user with `displayLocale=vi-VN` may have an invoice in `100 USD`, `100 EUR`, or `100 VND`. The `show` method still accepts a `Currency` so language preference is never equated with currency unit. A `Locale.US` formatter may render a different symbol for EUR, yet it is still the **unit determined by the `currency` argument**.

## 9. Presentation after conversion

Suppose the backend has produced two entities:

```text
sourceMoney  = 100.00 USD
targetMoney  = 91.50 EUR
displayLocale = vi-VN
```

A proper screen might display:

```text
Original amount:    100,00 USD
Illustrative rate:  1 USD = 0,9150 EUR
Converted amount:   91,50 EUR
Quoted at:          2026-10-28T00:00:00Z
```

These representations are **user-facing content illustrations**, not guaranteed `NumberFormat`/`DateTimeFormatter` output strings across every JDK. Locale can change symbols, spacing, and currency code placement. Applications should format according to `Locale` and explicitly show the ISO 4217 code whenever symbols might be ambiguous.

If a screen merely changes the output to “€100.00” without showing an exchange rate or arithmetic result, **no conversion was performed**. Never report “Converted successfully” just because a different symbol appeared in the UI.

Other details to include depending on product requirements: buy/sell rate, fees, total deductions, net amount received, quote expiration, transaction ID, and an indicator of whether the displayed value is an estimate or locked in.

## 10. Storage and APIs: money is amount + currency

To keep frontend and backend independent of language or grouping separators, an explicit data contract is required.

The JSON example below uses **canonical decimal strings** to preserve precision across systems that do not natively preserve decimals:

```json
{
  "source": {
    "amount": "100.00",
    "currency": "USD"
  },
  "quote": {
    "baseCurrency": "USD",
    "counterCurrency": "EUR",
    "counterPerBase": "0.9150",
    "asOf": "2026-10-28T00:00:00Z",
    "roundingMode": "HALF_EVEN"
  },
  "result": {
    "amount": "91.50",
    "currency": "EUR"
  }
}
```

This is a **contract example**, not the default JSON format automatically generated by Java/Jackson. An API can use JSON numbers if precision/scale and client limits are strictly specified; decimal strings are often advantageous when interoperating with JavaScript or accounting systems.

Do not send machine-computable values as `"€91,50"` or `"$100.00"` and expect the backend to guess the currency, decimal separator, or real amount from text. **Display strings are produced at the UI layer and never replace canonical data.**

In a database, a monetary record typically includes a `DECIMAL/NUMERIC` column with properly chosen precision and scale alongside a currency code. When a conversion occurs, audit requirements may require keeping the source amount, target amount, applied quote/rate, timestamp, and fees. **Do not silently overwrite the source amount with the target amount** if the business requires traceability.

## 11. Currency symbols and codes do not replace exchange rates

### 11.1. Changing the symbol

`currency.getSymbol(locale)` or a formatter can yield symbols such as `$`, `US$`, `€`, etc. This is merely text representing the currency unit. It can vary by language, and in some cases the ISO code itself is displayed instead of a symbol.

**Do not parse symbols to determine the “canonical currency code”**: the same `$` symbol can be used for USD, CAD, AUD, and other currencies; users may also enter symbols inconsistently with the locale.

### 11.2. Changing the ISO 4217 code

Even if you only change the string `"USD"` to `"EUR"` in a DTO, the system has only changed the **label unit**, not the `amount`. An object like:

```json
{"amount":"100.00","currency":"EUR"}
```

means **100 EUR**, not “100 USD to be converted to EUR later.” If the original value was 100 USD, changing the code while keeping the amount at 100.00 mislabels the data.

You must create a **new result record** after the calculation and rounding policy, and record the provenance of the result if needed.

### 11.3. Choosing another locale does not change the currency code either

Switching from `Locale.US` to `Locale.FRANCE` may cause `NumberFormat.getCurrencyInstance(...)` to pick a different default currency, but no rate multiplication occurs. Therefore, in UIs displaying multiple currencies, pass the **amount's actual Currency** to the formatter and configure appropriate fraction digits.

## 12. Exchange rates: direction, timestamp, and continuous change

An exchange rate is only meaningful when paired with a **currency pair** and **direction**. For example:

```text
quote:
  base = USD
  counter = EUR
  rate = 0.9150 EUR / 1 USD
```

If the source is 100 USD, the calculation is `100 × 0.9150 = 91.50 EUR`. If the source is EUR and you need USD, you must not use the exact same multiplication: you need a quote for the EUR→USD direction or invert the rate **according to business rules**, with appropriate precision and rounding. Buy and sell rates are not necessarily exact reciprocals.

Exchange rates are also time-sensitive. A value of `0.9150` cannot be treated as “valid forever.” You must specify when it applied, what its source was, whether it is still valid, and what kind of rate it is (reference, bid, ask, or locked transaction rate).

**Do not turn a formatter into an exchange-rate service.** `Currency` in the JDK does not fetch market prices, `NumberFormat` does not connect to quote providers, and `Locale` does not supply FX effective timestamps.

## 13. Rounding considerations in business logic

Rounding a value in the UI differs from determining a valid settlement amount:

- `NumberFormat.setMaximumFractionDigits(2)` limits the **display string**; it does not update the original `BigDecimal`.
- `BigDecimal.setScale(2, RoundingMode.HALF_EVEN)` produces a **rounded decimal value** according to an explicit policy.
- `Currency.getDefaultFractionDigits()` provides standard decimal-place metadata; some cash transactions have specific increment rounding rules, such as 0.05 units, which cannot be inferred from scale alone.
- Transaction fees and spreads may be applied before or after conversion; the order and timing of rounding must be fixed by contract.
- Depending on the product, an “estimated” displayed amount may differ from the locked amount once a quote expires; both must be distinguished.
- Avoid performing multi-step multiplications/divisions and rounding arbitrarily at each step, as different results can arise from the same input rate.

`RoundingMode.UNNECESSARY` can be used to detect disallowed rounding when a value has remaining fractional digits, though it throws `ArithmeticException` if the data requires rounding; choose it only when the contract strictly requires exactness at that scale.

## 14. Java design to prevent mislabeling

If you store only `BigDecimal amount` without storing `Currency`, code can easily pass the amount to the wrong country's formatter. Model it explicitly:

```java
record Money(BigDecimal amount, Currency currency) {}
```

This is a record declaration that can be placed at package level or inside a class, not a standalone program. When constructing the object, ensure `amount` and `currency` are validated against `null` if business rules require it. A Java record is only a data structure; it **does not automatically perform** any conversion.

A service should expose unambiguous business APIs:

```text
convert(sourceMoney, quote, targetCurrency)
    → Money(amountAfterRateAndRounding, targetCurrency)

format(money, displayLocale)
    → String localizedLabel
```

Avoid ambiguous APIs such as:

```text
changeCurrency(sourceMoney, "EUR")
    → ???
```

The name `changeCurrency` could be interpreted as relabeling or performing a conversion. If a product has a currency-exchange operation, give it a clear name like `convertCurrency`, enforce quote validation, and return a separate result object.

### NumberFormat in multi-user applications

`NumberFormat` is mutable and not thread-safe by default when used concurrently by multiple threads. On a Java server, create a separate instance per request/locale or manage a thread-safe cache; never let two requests call `setCurrency` on a shared global formatter and accidentally display USD/EUR to the wrong user.

Do not call `Locale.setDefault` to choose a region per request. The default locale is JVM-wide state and can alter formatting for other concurrent requests.

## 15. Common mistakes

| Mistake | Consequence | Mitigation |
| --- | --- | --- |
| Calling `setCurrency(EUR)` on a USD formatter and treating it as conversion | 100 USD can be displayed as 100 EUR | Compute `amount × rate` and create a new `Money` |
| Changing the `currency` field in a DTO while keeping the amount unchanged | Data is labeled with the wrong unit | Only change currency as part of a business calculation |
| Inferring settlement currency from `Locale.getDefault()` | The same transaction may switch currencies across deployments | Store currency in transaction data |
| Using the `$` symbol as a currency code | Ambiguity across multiple currencies | Use ISO 4217 codes |
| Using `double` for monetary values requiring decimal accuracy | Binary representation errors and hard-to-control rounding | Use `BigDecimal` from decimal strings |
| Multiplying by a rate in the wrong direction | Incorrect target amount | Have the quote specify base/counter and rate units |
| Using an exchange rate without a timestamp | Hard to audit and may be expired | Record quote source and timestamp |
| Only calling `setCurrency(JPY)` and trusting the formatter to update fraction digits | Wrong precision displayed | Set min/max fraction digits per policy |
| Re-parsing `"€91,50"` to persist money | Locale-dependent and risks losing precision | Pass amount and currency in a canonical contract |
| Comparing two formatted strings to compare values | Suffixes, separators, and rounding may differ | Compare `Money` values in the same unit or convert explicitly |
| Treating a hypothetical rate as a live rate | Misleads about transaction validity | Clearly mark quotes and verify real sources |
| Sharing a mutable formatter across multiple requests | Risk of swapping currency labels between requests | Use per-request formatters or thread-safe mechanisms |

## 16. Testing both arithmetic and presentation

There should be **two independent test groups**.

### Group A — verify conversion is a contracted calculation

1. When source is `Money(100.00, USD)` and quote is `0.9150 EUR per USD`, result must be `Money(91.50, EUR)` with `HALF_EVEN`/scale 2.
2. Source is not mutated; quote is not mutated.
3. If source is EUR but quote base is USD, it must reject rather than silently multiply by the wrong rate direction.
4. Boundary cases must be tested, such as zero amount, negative amount (if refunds are supported), very large numbers, zero/negative rates, or expired quotes per policy.
5. For currencies without two default decimal places, the exact business scale/rounding must be used.
6. Round-trip conversions, fees, and spreads must be tested against actual formulas; do not assume converting back and forth preserves the original amount due to rounding and spread differences.

### Group B — verify the formatter only handles presentation

1. `NumberFormat.getCurrencyInstance(Locale.US)` and `getCurrencyInstance(Locale.FRANCE)` may render differently, yet the original `Money` object remains unchanged.
2. `setCurrency(EUR)` changes the formatter's Currency, **not** `Money.amount()` or `Money.currency()`.
3. Formatting the same `Money` in two locales must not alter the domain's exchange rate or currency code.
4. Do not hardcode full Unicode strings for many locales without pinning JDK/CLDR/provider; non-breaking spaces, symbols, and signs may vary.
5. For formatters used in multi-threaded services, include concurrency tests or isolate instances to prevent mixed configuration.
6. The UI should display the proper currency name/code if the symbol could be ambiguous.

### Self-check exercises

**Question 1.** Given `amount=100.00`, `currency=USD`. After calling `formatter.setCurrency(EUR)`, what is `amount`?

**Answer:** Still 100.00, if no other operation was performed. The string may contain the EUR symbol, but **this is not a converted 100 EUR**.

**Question 2.** Given the hypothetical rate `0.9150 EUR per USD`, how much is 100.00 USD in EUR before fees?

**Answer:** 91.500000 EUR before scale rounding, typically represented as 91.50 EUR with scale 2 and the defined policy.

**Question 3.** A `vi-VN` user buys a product priced at 50 USD. Does changing the display locale to `en-US` mean changing the settlement currency to USD?

**Answer:** No; the transaction was already in USD. Only presentation conventions may change. If it were originally in VND, changing the locale would not create USD either.

**Question 4.** Can `Currency.getSymbol(Locale.US)` uniquely identify the ISO 4217 code for any `$` symbol?

**Answer:** No; multiple currencies can share a symbol. Store and pass the currency code separately.

**Question 5.** Why must the currency pair and rate direction be stored alongside the number `0.9150`?

**Answer:** Because `0.9150 EUR/USD` means something different from `0.9150 USD/EUR`; the multiplication/division and result differ. Effective timestamp and fee/rounding policies are also needed.

**Question 6.** Does `NumberFormat.setCurrency(JPY)` guarantee the formatter displays 0 decimal places when it was previously created for USD?

**Answer:** No; `setCurrency` does not automatically update minimum/maximum fraction digits. You must configure them according to the target currency or application policy.

## 17. Key takeaways

- **`Currency` is unit metadata; `Locale` is presentation context; `NumberFormat` produces strings. None of these three provides or applies exchange rates.**
- Replacing `$` with `€` or `"USD"` with `"EUR"` while keeping the amount unchanged is **relabeling**, not conversion.
- Proper conversion requires **source amount + source currency + target currency + directed rate + timestamp + rounding/fees policy**.
- **`BigDecimal`** is suited for decimal monetary calculations; **`NumberFormat`** is suited for user-facing formatting. Never use formatted strings in place of canonical monetary amounts.
- A conversion result must be a **new value paired with a new unit**; source objects and quote history should be retained when required by the business.
- Send explicit amount and currency code across APIs and databases; format by locale only at display time.
- For real transactions, the rate in this guide is an example, not a market price. Use approved quotes and preserve auditability.

**Official Java SE 17 documentation:**

- [`Currency` — java.util.Currency](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Currency.html)
- [`NumberFormat` — java.text.NumberFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html)
- [`BigDecimal` — java.math.BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html)
