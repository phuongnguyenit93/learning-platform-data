# Testing Decimals, Percentages, Currencies, and Full-Input Parsing in Java

## 1. Why Do Three Number Formatting Types Need Separate Tests?

In Java Core Localization, the same numeric quantity can pass through three different representations:

- **Standard decimals:** `1234.50` may display as `1,234.50` in `en-US`, `1.234,50` in `de-DE`.
- **Percentages:** a domain ratio of `0.125` may display as `12.5%`; the `%` sign and whitespace placement depend on locale.
- **Currencies:** amount `1234.50` plus currency code `USD` may display as `$1,234.50`, `1.234,50 $`, or another locale-specific expression.

A test suite that checks only whether `format(value)` outputs a "good-looking" string misses many bugs: a parser accepts a **leading prefix** and ignores the remainder, two locales interpret the same separator differently, percentages are multiplied/divided by 100 incorrectly, amounts are rounded silently, currencies are inferred from ambiguous symbols, or the parser accepts `NaN` in fields allowing only finite numbers.

This lesson belongs to **Testing and Pitfalls**. Its focus is designing intentional tests for **decimal / percentage / currency**, especially enforcing **full-input consumption**: accept input only when the parser consumes the entire string, leaves no trailing characters, produces the right value type, and satisfies domain rules.

### Learning Objectives

After this lesson, you can:

1. Construct `NumberFormat` formatters/parsers for an explicit `Locale`, choosing the right type among decimal, percent, and currency.
2. Use `ParsePosition` to distinguish **parsing a prefix** from **parsing the entire string**.
3. Use `DecimalFormat.setParseBigDecimal(true)` for exact decimal handling while rejecting `NaN` and infinity for business fields that disallow them.
4. Understand that a percentage represents a **ratio**: `12.5%` is `0.125` in the standard model, not `12.5`.
5. Separate amount and ISO currency code from locale-specific currency symbols and names.
6. Write a test matrix covering positive, negative, boundary, Unicode whitespace, rounding, locale mismatch, and garbage inputs.
7. Distinguish **consuming the whole input** from **validating syntax/grouping rules**: a string can be fully consumed by the parser yet still violate input policy.
8. Design tests that do not mistake valid CLDR/JDK data differences for business bugs.

## 2. Separating Four Quality Conditions: Format, Parse, Consumed, and Domain

A numeric input should not be deemed valid merely because `NumberFormat.parse(...)` returns a `Number`.

There are **four distinct verification layers**:

| Layer | Question | Example bug |
| --- | --- | --- |
| **Formatting** | Does the domain value render properly for the locale, currency, precision, and rounding? | `0.125` is printed as `0.125%` instead of `12.5%` |
| **Parsing** | Does the formatter read the input string into a value? | An `en-US` parser misreads `de-DE` comma decimals |
| **Full consumption** | Did the parser consume **all** of the input? | `"1,234.50oops"` reads only `"1,234.50"` |
| **Validation** | Does the input obey syntax and domain policy? | `"12,34.50"` has wrong grouping yet may still be accepted by the parser |

Finally comes **data preservation**: does `format → parse` preserve the original numeric value, scale, and type? When formatting rounds, the answer can be **no**, even if all four conditions above pass.

### A Safe Input Pipeline

```text
Raw input + source locale + field kind
                |
        Size/character limits
                |
        Parser for exact field kind
                |
        ParsePosition: fully consumed?
                |
        Is value type valid?
                |
        Validate grouping, scale,
        range, unit/currency?
                |
        Typed domain value
                |
        Persist in canonical schema
```

Obtain the locale from the **input source context**, never guessing from `Locale.getDefault()` of the JVM and never relying on characters that look like commas or dots. If data arrives from a machine-to-machine API, use a canonical decimal schema instead of routing through a localized UI parser.

## 3. Java Factories You Must Choose Properly

Java SE 17 provides these methods:

| Field kind | Factory | Domain example | `en-US` display example |
| --- | --- | --- | --- |
| Decimal | `NumberFormat.getNumberInstance(locale)` | `BigDecimal("1234.50")` | `1,234.50` |
| Percent | `NumberFormat.getPercentInstance(locale)` | Ratio `BigDecimal("0.125")` | `12.5%` if 1 fraction digit allowed |
| Currency | `NumberFormat.getCurrencyInstance(locale)` | `1234.50` + `USD` | `$1,234.50` |
| Integer | `NumberFormat.getIntegerInstance(locale)` | `1234` | `1,234` |

**Crucial distinction:** `getIntegerInstance` is configured to parse integer parts and can stop at the decimal separator. Do not use it to parse a decimal field and expect it to consume `"12.5"` completely.

The returned object is usually `DecimalFormat` across common locales/providers, yet `NumberFormat` is an abstract class and the factory API does not promise every implementation is always `DecimalFormat`. When calling `setParseBigDecimal(true)`, check the type before casting:

```java
NumberFormat base = NumberFormat.getNumberInstance(locale);
if (!(base instanceof DecimalFormat decimal)) {
    throw new IllegalStateException("DecimalFormat required");
}
decimal.setParseBigDecimal(true);
```

This snippet illustrates code **inside a method**, requiring `import java.text.*`. Do not cast unconditionally in a library that must support arbitrary custom locale providers.

**Do not share a mutable `DecimalFormat`** whose currency, fraction digits, or pattern are altered across multiple threads. Tests should create fresh instances; production code also needs proper lifecycle management or synchronization.

## 4. Minimal Test Matrix

Do not lump all numeric types into one "formats nicely" test. Each row checks a distinct assumption.

| Category | Input / value | Expected outcome |
| --- | --- | --- |
| Decimal `en-US` | `"1,234.50"` | Value `1234.50`, 100% consumed |
| Decimal `de-DE` | `"1.234,50"` | Value `1234.50`, 100% consumed |
| Locale mismatch | `"1.234,50"` parsed with `en-US` | Must not be accepted as complete valid input |
| Garbage suffix | `"1,234.50oops"` | Rejected because only a prefix was parsed |
| Invalid grouping | `"12,34.50"` `en-US` | Rejected if policy mandates standard grouping |
| Empty / whitespace | `""`, `" "` | Handled per input policy; never silently treated as 0 |
| Percent | `"12.5%"` `en-US` | Ratio `0.125`, 100% consumed |
| Percent missing sign | `"12.5"` with percent parser | Fails under the applicable pattern |
| Percent suffix | `"12.5%extra"` | Rejected |
| Currency | `"$1,234.50"` `en-US` | Amount `1234.50` and currency `USD` from **context** |
| Currency suffix | `"$1,234.50oops"` | Rejected |
| Currency wrong symbol | `"€1,234.50"` with USD formatter | Not treated as valid USD |
| Fraction precision | `1.239` formatted to 2 digits | Formatting rounds; do not expect parse to recover `1.239` |
| Special numbers | `NaN`, infinity | Rejected if domain accepts only finite decimals |
| Signed zero | `-0` | Define explicitly whether negative zero sign matters |
| Unicode whitespace | U+0020, U+00A0, U+202F | Test each character explicitly; do not treat them identically |
| CLDR upgrade | Same locale, before/after JDK | Separate presentation changes from domain bugs |

Use the product's actual locales. `en-US` and `de-DE` are a strong starting point because grouping/decimal separators swap roles; add `fr-FR` to catch Unicode spaces and other locales with non-Latin numbering systems when required.

## 5. `ParsePosition`: Mandatory for Verifying Full Strings

`NumberFormat.parse(String, ParsePosition)` attempts to parse starting at `ParsePosition.getIndex()`, then advances the index to where parsing stopped. The method can:

- Return a `Number` with index **equal to input length**: the parser read everything.
- Return a `Number` with index **less than input length**: only a prefix was read.
- Return `null` or fail to advance when input cannot be parsed; `errorIndex` helps locate the failure.
- Return a `Number` subtype unsuitable for the domain, such as `Double.NaN` even when `setParseBigDecimal(true)` is enabled.

Example:

```text
input:          1,234.50oops
parsed number:  1234.50
end index:      8
input length:   12

Result: REJECT — unconsumed characters remain
```

**Simple check function:**

```java
ParsePosition position = new ParsePosition(0);
Number number = decimalFormat.parse(input, position);

boolean consumedAll = number != null
        && position.getIndex() == input.length();
```

Yet even `consumedAll == true` confirms only **length**, not valid grouping or currency according to the domain. Name the helper `parseFully` or `consumedAll`, rather than `validateEntireFinancialInput`, if it does not yet perform domain validation.

### Avoid Confusing `ParseException` with `ParsePosition`

The `parse(String)` overload throws `ParseException` when it cannot start parsing, yet it can still accept a **prefix** and ignore the rest. The `parse(String, ParsePosition)` overload lets you inspect the offset, normally returns `null` on failure, and avoids using exceptions for routine pass/fail control flow.

For UI forms, distinguish "could not start parsing", "unparsed trailing text", "wrong grouping separators", "value out of range", and "wrong currency" to give helpful user feedback.

## 6. Java 17+: Full-String Parser for All Three Types

Create `FullInputNumberDemo.java`:

```java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Currency;
import java.util.Locale;

public class FullInputNumberDemo {
    enum Kind { DECIMAL, PERCENT, CURRENCY }

    static DecimalFormat formatter(
            Locale locale, Kind kind, Currency currency) {
        NumberFormat base = switch (kind) {
            case DECIMAL -> NumberFormat.getNumberInstance(locale);
            case PERCENT -> NumberFormat.getPercentInstance(locale);
            case CURRENCY -> NumberFormat.getCurrencyInstance(locale);
        };
        if (!(base instanceof DecimalFormat decimal)) {
            throw new IllegalStateException("DecimalFormat required");
        }
        if (kind == Kind.CURRENCY) {
            decimal.setCurrency(currency);
        }
        decimal.setParseBigDecimal(true);
        return decimal;
    }

    static BigDecimal parseFully(
            String input, Locale locale, Kind kind,
            Currency currency) {
        if (input == null || input.isEmpty()) {
            throw new IllegalArgumentException("Empty input");
        }
        DecimalFormat format = formatter(locale, kind, currency);
        ParsePosition at = new ParsePosition(0);
        Number parsed = format.parse(input, at);

        if (!(parsed instanceof BigDecimal decimal)
                || at.getIndex() != input.length()) {
            throw new IllegalArgumentException(
                    "Incomplete or invalid input");
        }
        return decimal;
    }

    static void test(String label, String raw,
            Locale locale, Kind kind, Currency currency) {
        try {
            BigDecimal result =
                    parseFully(raw, locale, kind, currency);
            System.out.println(label + ": " + result.toPlainString());
        } catch (IllegalArgumentException ex) {
            System.out.println(label + ": REJECT");
        }
    }

    public static void main(String[] args) {
        Currency usd = Currency.getInstance("USD");
        test("decimal US", "1,234.50",
                Locale.US, Kind.DECIMAL, usd);
        test("decimal DE", "1.234,50",
                Locale.GERMANY, Kind.DECIMAL, usd);
        test("decimal suffix", "1,234.50oops",
                Locale.US, Kind.DECIMAL, usd);
        test("wrong locale", "1.234,50",
                Locale.US, Kind.DECIMAL, usd);

        test("percent", "12.5%",
                Locale.US, Kind.PERCENT, usd);
        test("percent suffix", "12.5%extra",
                Locale.US, Kind.PERCENT, usd);
        test("percent missing symbol", "12.5",
                Locale.US, Kind.PERCENT, usd);

        test("currency", "$1,234.50",
                Locale.US, Kind.CURRENCY, usd);
        test("currency suffix", "$1,234.50oops",
                Locale.US, Kind.CURRENCY, usd);
        test("currency wrong symbol", "€1,234.50",
                Locale.US, Kind.CURRENCY, usd);
        test("NaN", "NaN",
                Locale.US, Kind.DECIMAL, usd);
    }
}
```

Run:

```bash
javac -encoding UTF-8 FullInputNumberDemo.java
java FullInputNumberDemo
```

Stdout on a JDK with standard `en-US`/`de-DE` formats, verified against the Java runtime:

```text
decimal US: 1234.50
decimal DE: 1234.50
decimal suffix: REJECT
wrong locale: REJECT
percent: 0.125
percent suffix: REJECT
percent missing symbol: REJECT
currency: 1234.50
currency suffix: REJECT
currency wrong symbol: REJECT
NaN: REJECT
```

**Important explanations:**

1. `12.5%` becomes `0.125` because percent `DecimalFormat` uses a multiplier of 100. The domain value represents a **ratio**, not percentage points.
2. `"1.234,50"` under `Locale.US` may read only up to `"1.234"`, so it must be rejected because it was not fully consumed.
3. `"1,234.50oops"` can yield `BigDecimal("1234.50")` **yet has a trailing tail**; it must not be accepted.
4. `NaN` can be returned as a `Double` even with `setParseBigDecimal(true)`; checking `instanceof BigDecimal` keeps it out of finite decimal domains.
5. `CURRENCY` here takes the **expected currency from context**. When `NumberFormat.parse` parses a number successfully, it **does not provide a trustworthy `Currency` inferred from the symbol**. The parse result is the amount; the currency is a separate domain attribute that must be validated at the appropriate layer.
6. The function named `parseFully` enforces only **full-string consumption and `BigDecimal`**, not strict grouping grammar, scale, or range; a later section adds that.

With different locale providers (SPI/HOST), currency symbol patterns may vary; if tests depend on exact literal output, pin the provider/build or construct fixtures against a verified contract.

## 7. Percent: Separating Ratio, Percentage String, and Percentage Points

This is one of the most severe testing pitfalls. Three concepts exist:

| Value | Meaning | Example |
| --- | --- | --- |
| `0.125` | Ratio (12.5 percent on a 0–1 scale) | Multiplier used in calculations |
| `12.5%` | **Display** of ratio `0.125` | `NumberFormat.getPercentInstance` |
| `12.5` | Value measured in percentage units, not a ratio | If stored as percent points, conversion must be explicit |

With `getPercentInstance(Locale.US)`:

```java
NumberFormat percent =
        NumberFormat.getPercentInstance(Locale.US);
percent.setMaximumFractionDigits(1);

String text = percent.format(new BigDecimal("0.125"));
// "12.5%"
```

This is an **illustrative snippet inside a method**. When parsing `"12.5%"` with a percent formatter configured with `setParseBigDecimal(true)`, the result is normally `BigDecimal("0.125")`, not `12.5`. **Do not multiply by 100 again when constructing the domain value**, and do not divide by 100 again if the parser already did.

### Percent Tests to Include

- `0` → `0%` in the default `en-US` pattern.
- `0.125` → `12.5%` when configured for 1 decimal digit.
- `1` → `100%`; if the domain restricts ratios to 0–1, validate the range.
- Negative values if allowed by the domain, e.g. `-0.025` → `-2.5%`.
- Values greater than 1 if business logic allows >100% growth.
- Leading/trailing `%` sign and Unicode spaces depending on locale.
- Inputs missing `%`, inputs with trailing characters, inputs containing only the symbol.
- Rounding when `12.34%` displays to one decimal place as `12.3%`; parsing back recovers only the displayed value.

**Choose clear semantics:** for a "discount rate" you may store ratio `0.125`; for a "change of 12.5 percentage points" that is a different quantity. Domain types or field names should state this clearly, e.g., `discountRate` rather than an ambiguous `percent`.

## 8. Java 17+: Formatting Tests for Decimal, Percent, and Currency

Create `NumberFormattingMatrixDemo.java`:

```java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.util.Currency;
import java.util.List;
import java.util.Locale;

public class NumberFormattingMatrixDemo {
    public static void main(String[] args) {
        BigDecimal amount = new BigDecimal("1234.50");
        BigDecimal ratio = new BigDecimal("0.125");
        Currency usd = Currency.getInstance("USD");

        for (String tag : List.of("en-US", "de-DE")) {
            Locale locale = Locale.forLanguageTag(tag);

            NumberFormat decimal =
                    NumberFormat.getNumberInstance(locale);
            decimal.setMinimumFractionDigits(2);
            decimal.setMaximumFractionDigits(2);

            NumberFormat percent =
                    NumberFormat.getPercentInstance(locale);
            percent.setMaximumFractionDigits(1);

            NumberFormat money =
                    NumberFormat.getCurrencyInstance(locale);
            money.setCurrency(usd);

            System.out.println(tag + " | decimal="
                    + decimal.format(amount) + " | percent="
                    + percent.format(ratio) + " | money="
                    + money.format(amount));
        }

        System.out.println("amount unchanged="
                + amount.equals(new BigDecimal("1234.50")));
        System.out.println("ratio unchanged="
                + ratio.equals(new BigDecimal("0.125")));
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 NumberFormattingMatrixDemo.java
java NumberFormattingMatrixDemo
```

Example stdout on a tested JDK using CLDR locale data:

```text
en-US | decimal=1,234.50 | percent=12.5% | money=$1,234.50
de-DE | decimal=1.234,50 | percent=12,5 % | money=1.234,50 $
amount unchanged=true
ratio unchanged=true
```

The `de-DE` line contains **U+00A0 NO-BREAK SPACE** between the number and `%`/`$` on the reference runtime. Do not replace it with an ASCII space in golden strings if testing exact Unicode. On a different JDK/provider, presentation output may change; the `amount unchanged` and `ratio unchanged` lines check domain invariants.

**Why test output as well?** Even when domain values are right, display can still break due to missing `setCurrency`, confusing percent and number factories, wrong min/max fraction digits, or formatting with the host's default locale. Domain tests and presentation tests complement—never replace—each other.

## 9. Currency: Amount, ISO Code, and Symbol Must Be Tested Separately

A `Currency` object represents a currency identified by **code**, such as `USD`, `EUR`, or `VND`. Symbols like `$`, `€`, or locale abbreviations serve presentation only and are **not unique currency keys**.

Example:

```java
Currency currency = Currency.getInstance("USD");
NumberFormat format =
        NumberFormat.getCurrencyInstance(Locale.GERMANY);
format.setCurrency(currency);
String output = format.format(new BigDecimal("1234.50"));
```

This is a **code snippet inside a method**. The German locale dictates separator/symbol conventions, while the domain currency remains USD. A user living in Germany can pay in USD; never infer that all their transactions are EUR from `Locale.GERMANY`.

### Currency Tests Must Distinguish

1. **Amount parse:** does `"$1,234.50"` yield the right decimal amount?
2. **Currency identity:** is the business-supplied currency code `USD`?
3. **Display symbol:** do the symbol, placement, and spacing match presentation policy for the locale?
4. **Mismatch:** when `USD` is required, how is an input displaying `EUR` handled? Never extract a `BigDecimal` and silently label it `USD`.
5. **Fraction digits:** JPY, USD, and KWD have different minor-unit conventions; business scale/rounding policies must be explicit.
6. **Ambiguity:** `$` represents multiple currencies; never guess a currency code from a lone text symbol.
7. **Negative amounts:** refunds/chargebacks can carry a minus sign; accounting formats and business policies may differ.
8. **Locale upgrades:** symbol placement and no-break spaces can change across CLDR/JDK releases, so snapshot tests should record runtime info.

### Choosing a Schema for Money

```json
{
  "amount": "1234.50",
  "currency": "USD"
}
```

This is a machine-to-machine JSON example with a schema-defined decimal string, **not** a localized price. In a database, choose `DECIMAL`/`NUMERIC` with explicit precision/scale and a separate currency code column. Use `BigDecimal` in Java; never calculate money with `double` or use `NumberFormat.format(amount)` as a data source.

**Parser limitation:** `NumberFormat.parse` reads numeric values matching a currency pattern, not a general currency-code verifier over arbitrary text. If the UI has a dedicated currency selector, treat it as a controlled input; if parsing multi-currency free text, use a unit-aware parser and validate the resulting ISO code against domain rules.

## 10. Full-Input Consumption Does Not Imply Strict Grouping

This requires a dedicated test. On common JDKs with `DecimalFormat`, the input:

```text
12,34.50
```

can be **fully consumed** by an `en-US` number parser and return `1234.50`, even though the grouping separator is not placed in standard `1,234.50` groups.

The condition:

```java
position.getIndex() == input.length()
```

is **necessary** to reject trailing suffixes, yet **insufficient** to guarantee the input obeys strict grouping grammar. i18n parsers are often lenient so they can read varied user inputs; financial workflows may demand stricter rules.

### Multi-Layer Validation Architecture

```text
Input "12,34.50"
          |
      full parse
          |
    parsed = 1234.50
    consumed = true
          |
      lexical policy
          |
   Invalid grouping
          |
        REJECT
```

Lexical validation must match the input kind and locale. **Do not apply a single ASCII comma/dot regex across all locales**: `fr-FR` can use U+202F, `ar-EG` has different digits and separators, and Indian numbering uses non-3-3-3 grouping. If business logic accepts only one fixed machine structure, prefer a canonical grammar without grouping rather than overly complex localized grammars.

## 11. Java 17+: Simple Strict Policy for en-US Decimals

The following example is intentionally scoped to a **positive `en-US` number format with no exponent**, permitting either comma-separated three-digit groups or ungrouped digits, 1–2 fractional digits, and no `+/-` sign.

Create `StrictGroupingDemo.java`:

```java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;
import java.util.regex.Pattern;

public class StrictGroupingDemo {
    private static final Pattern US_DECIMAL = Pattern.compile(
            "(?:0|[1-9][0-9]*|"
            + "[1-9][0-9]{0,2}(?:,[0-9]{3})+)"
            + "(?:\\.[0-9]{1,2})?");

    static BigDecimal parse(String input) {
        if (input == null || !US_DECIMAL.matcher(input).matches()) {
            throw new IllegalArgumentException("Invalid syntax");
        }

        NumberFormat base = NumberFormat.getNumberInstance(Locale.US);
        if (!(base instanceof DecimalFormat formatter)) {
            throw new IllegalStateException("DecimalFormat required");
        }
        formatter.setParseBigDecimal(true);
        ParsePosition pos = new ParsePosition(0);
        Number value = formatter.parse(input, pos);

        if (!(value instanceof BigDecimal result)
                || pos.getIndex() != input.length()) {
            throw new IllegalArgumentException("Invalid value");
        }
        return result;
    }

    static void test(String input) {
        try {
            System.out.println(input + " => " + parse(input));
        } catch (IllegalArgumentException ex) {
            System.out.println(input + " => REJECT");
        }
    }

    public static void main(String[] args) {
        test("1234.50");
        test("1,234.50");
        test("12,34.50");
        test("1,234.50xyz");
        test("0012.50");
        test("1,234.567");
        test("0.50");
    }
}
```

```bash
javac StrictGroupingDemo.java
java StrictGroupingDemo
```

```text
1234.50 => 1234.50
1,234.50 => 1234.50
12,34.50 => REJECT
1,234.50xyz => REJECT
0012.50 => REJECT
1,234.567 => REJECT
0.50 => 0.50
```

**Intentional scope:**

- This regex is **not** meant for `de-DE`, `fr-FR`, Arabic numerals, or negative numbers.
- `1234.50` without grouping is valid under this sample policy; `1,234.50` with valid grouping is also valid.
- `0012.50` is rejected because the policy disallows leading zeros; another domain might allow them.
- A maximum of 2 fractional digits is enforced by policy, not by Java itself.
- `regex.matches()` checks the **entire string**; afterward the parser still checks full consumption and value type.
- For real monetary amounts, also enforce domain scale/precision, currency, rounding, min/max, and input length limits.

If strict localized grammar is needed across multiple languages, base it on locale data and appropriate parser/ICU rules rather than copying a US regex across the entire application.

## 12. Rounding: `format → parse` May Not Preserve the Original Number

A common broken test is:

```java
BigDecimal original = new BigDecimal("1.239");
String text = currencyFormatter.format(original);
BigDecimal restored = parse(text);
assertEquals(original, restored); // Not a universal invariant
```

If the formatter displays only two decimal digits, `1.239` can become `1.24`. The parser has no way to recover the discarded third digit. A bad test blames localization, while **the formatter is faithfully executing its presentation policy**.

### Java 17+: Demonstrating Precision Loss in Round-Trip

Create `RoundingRoundTripDemo.java`:

```java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class RoundingRoundTripDemo {
    public static void main(String[] args) throws Exception {
        DecimalFormat formatter = new DecimalFormat(
                "#,##0.00",
                DecimalFormatSymbols.getInstance(Locale.US));
        formatter.setParseBigDecimal(true);

        BigDecimal original = new BigDecimal("1.239");
        String shown = formatter.format(original);
        BigDecimal parsed = (BigDecimal) formatter.parse(shown);

        System.out.println("original=" + original);
        System.out.println("shown=" + shown);
        System.out.println("parsed=" + parsed);
        System.out.println("same numeric value="
                + (original.compareTo(parsed) == 0));
    }
}
```

```bash
javac RoundingRoundTripDemo.java
java RoundingRoundTripDemo
```

```text
original=1.239
shown=1.24
parsed=1.24
same numeric value=false
```

**Test according to contract:** if the domain must preserve `1.239`, keep the untouched `BigDecimal` in domain/persistence and format `1.24` only for the UI. If business rules require rounding to 2 decimal places **before posting**, perform that with explicit `setScale(2, roundingMode)` or defined monetary logic **in the domain**, not as an accidental side effect of a display formatter.

### `BigDecimal.equals` Differs from `compareTo`

`new BigDecimal("1.20").equals(new BigDecimal("1.2"))` is `false` due to differing scale, whereas `compareTo(...) == 0`. When testing parse/round-trip, decide whether **preserving scale** is a requirement. Never default to `equals` for all numeric assertions, and never ignore scale when the domain genuinely requires exact decimal places.

## 13. NaN, Infinity, and Negative Zero: Testing Edge Values

When `DecimalFormat.setParseBigDecimal(true)` is enabled, the parser normally returns `BigDecimal` for finite decimal numbers; however, special tokens such as **NaN** or **infinity** can return **`Double`**. `BigDecimal` has no representation for NaN/infinity.

Therefore:

```java
Number result = decimal.parse(input, position);
if (!(result instanceof BigDecimal)) {
    // Reject NaN, Infinity, and types unsuitable for the domain.
}
```

This is an illustrative snippet. If a system permits NaN in a domain like statistics, use a dedicated type/domain policy rather than forcing it into monetary amounts.

### Negative Zero

`double` distinguishes `+0.0` and `-0.0` at the bit representation level; `BigDecimal` does not preserve negative zero as a distinct sign value. Parsing `"-0"` with `setParseBigDecimal(true)` can produce `BigDecimal.ZERO`; if the domain must distinguish negative zero, store extra metadata or pick an appropriate numeric model.

Do not treat `-0` as a "valid negative monetary amount" just because the raw string starts with a minus sign. Financial domains typically require only value zero, while whether to accept the syntax `"-0"` is a validator decision.

### Very Large / Very Small Numbers

Test `Long.MAX_VALUE`, large `BigDecimal` values, numbers with many fractional digits, values near zero, and abnormally long inputs. Enforce resource bounds to prevent parsers from processing huge user strings or degrading performance. `setParseBigDecimal(true)` does not replace magnitude/precision limits.

## 14. Unicode Whitespace: Test Code Points, Never Guess by Eye

Some locales use Unicode whitespace as a grouping separator or between a number and a currency/percent symbol:

| Character | Code point | Common role |
| --- | --- | --- |
| ASCII SPACE | U+0020 | Standard space |
| NO-BREAK SPACE | U+00A0 | Non-breaking space |
| NARROW NO-BREAK SPACE | U+202F | Narrow non-breaking space |

For instance, `fr-FR` may display `1 234,5` with **U+202F**, while Russian and some currency patterns use U+00A0. JDK/CLDR updates can alter these characters.

If a test runs:

```java
assertEquals("1 234,5", actual);
```

it can fail even though both strings look identical; conversely, normalizing all spaces to ASCII just to pass tests can hide data parsing and line-breaking defects. When investigating, print the string's code points:

```java
static String codePoints(String s) {
    return s.codePoints()
            .mapToObj(cp -> String.format(
                    Locale.ROOT, "U+%04X", cp))
            .toList().toString();
}
```

This is an **illustrative method** requiring `import java.util.Locale;`. Include locale, JDK version, provider, currency, and output Unicode code points in regression reports.

### Java 17+: Probing the `fr-FR` Grouping Separator

Create `UnicodeGroupingProbe.java`:

```java
import java.text.DecimalFormatSymbols;
import java.text.NumberFormat;
import java.util.Locale;

public class UnicodeGroupingProbe {
    static String cps(String text) {
        return text.codePoints()
                .mapToObj(cp -> String.format(
                        Locale.ROOT, "U+%04X", cp))
                .toList().toString();
    }

    public static void main(String[] args) {
        Locale france = Locale.FRANCE;
        DecimalFormatSymbols symbols =
                DecimalFormatSymbols.getInstance(france);
        NumberFormat formatter =
                NumberFormat.getNumberInstance(france);

        String output = formatter.format(1234.5);
        System.out.printf(Locale.ROOT, "group=U+%04X%n",
                (int) symbols.getGroupingSeparator());
        System.out.println("number=" + cps(output));
    }
}
```

```bash
javac UnicodeGroupingProbe.java
java UnicodeGroupingProbe
```

Example result on a tested JDK:

```text
group=U+202F
number=[U+0031, U+202F, U+0032, U+0033, U+0034, U+002C, U+0035]
```

**Do not hard-code** that every JDK version uses U+202F for `fr-FR`. This test uses `DecimalFormatSymbols` to observe actual runtime behavior; if the product mandates a fixed input/output format, define an explicit contract and test that contract.

## 15. Automated Tests Must Separate Domain Tests from Presentation Snapshots

### 15.1. Domain Invariant Tests

Business values must remain unchanged:

- `BigDecimal("1234.50")` stays the decimal `1234.50` across locale changes.
- Ratio `BigDecimal("0.125")` stays ratio `0.125`.
- Currency code remains `"USD"` even when symbol/placement changes.
- Parsed values satisfy min/max/scale/precision.
- Changing the JVM default locale must not alter results **when** APIs pass locales explicitly.

For `BigDecimal`, compare with `compareTo` if policy checks numeric value only; compare with `equals` if exact scale must be preserved. Every test should state which criterion it uses.

### 15.2. Presentation Tests

Strings formatted for `Locale.US`, `Locale.GERMANY`, and `Locale.FRANCE` can differ in grouping marks, decimal separators, percent/currency symbols, and spacing. When testing literal output, record:

- JDK major/minor version and locale data;
- `java.locale.providers` (if configured);
- locale tag and Unicode numbering-system extension if present;
- currency code, rounding mode, min/max fraction digits;
- exact Unicode characters.

If a JDK upgrade causes CLDR to change a space character or symbol name, evaluate **whether it is a valid presentation update or an API contract violation**. Do not blindly update snapshots or mutate raw data to "match old results."

### 15.3. Property-Based / Data-Driven Testing

You can generate valid domain values and verify:

1. The formatter throws no errors over the valid amount range.
2. After formatting, a parser with the same locale recovers the **displayed value**, without expecting automatic recovery of pre-rounding precision.
3. When policy entails no rounding/precision loss, verify numeric round-trip with `BigDecimal.compareTo==0`.
4. Inputs with an appended invalid suffix are rejected when the API promises full-string parsing.
5. Inputs from a different locale are never silently accepted as wrong values without validation.
6. After parsing, value range, currency, and scale conform to the schema.

**Do not turn properties into false invariants:** `parse(format(x)) == x` does not hold universally due to rounding, grouping/provider/signed-zero differences, and scale. Constrain input assumptions and formatter configuration explicitly.

## 16. Java 17+: A Self-Checking Test Program Without JUnit

Use `AssertionError` to build a smoke suite runnable on JDK 17+ without `-ea`. Create `NumericParsingSmokeTest.java`:

```java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Currency;
import java.util.Locale;

public class NumericParsingSmokeTest {
    static BigDecimal parseAll(NumberFormat input, String raw) {
        if (!(input instanceof DecimalFormat format)) {
            throw new IllegalStateException("DecimalFormat required");
        }
        format.setParseBigDecimal(true);
        ParsePosition pos = new ParsePosition(0);
        Number value = format.parse(raw, pos);
        if (!(value instanceof BigDecimal decimal)
                || pos.getIndex() != raw.length()) {
            throw new IllegalArgumentException("Not fully parsed");
        }
        return decimal;
    }

    static void equal(BigDecimal expected, BigDecimal actual) {
        if (expected.compareTo(actual) != 0) {
            throw new AssertionError("Expected " + expected
                    + ", received " + actual);
        }
    }

    static void reject(NumberFormat format, String raw) {
        try {
            parseAll(format, raw);
            throw new AssertionError("Unexpected acceptance: " + raw);
        } catch (IllegalArgumentException expected) {
            // Rejection was expected.
        }
    }

    public static void main(String[] args) {
        equal(new BigDecimal("1234.50"),
                parseAll(NumberFormat.getNumberInstance(Locale.US),
                        "1,234.50"));
        equal(new BigDecimal("1234.50"),
                parseAll(NumberFormat.getNumberInstance(Locale.GERMANY),
                        "1.234,50"));

        reject(NumberFormat.getNumberInstance(Locale.US),
                "1,234.50tail");
        reject(NumberFormat.getNumberInstance(Locale.US),
                "1.234,50");

        equal(new BigDecimal("0.125"),
                parseAll(NumberFormat.getPercentInstance(Locale.US),
                        "12.5%"));
        reject(NumberFormat.getPercentInstance(Locale.US),
                "12.5%tail");

        NumberFormat currency =
                NumberFormat.getCurrencyInstance(Locale.US);
        currency.setCurrency(Currency.getInstance("USD"));
        equal(new BigDecimal("1234.50"),
                parseAll(currency, "$1,234.50"));
        reject(currency, "$1,234.50tail");

        reject(NumberFormat.getNumberInstance(Locale.US), "NaN");

        System.out.println("decimal: PASS");
        System.out.println("percent: PASS");
        System.out.println("currency: PASS");
        System.out.println("full-input: PASS");
        System.out.println("special-values: PASS");
    }
}
```

```bash
javac -encoding UTF-8 NumericParsingSmokeTest.java
java NumericParsingSmokeTest
```

Stdout when all checks pass:

```text
decimal: PASS
percent: PASS
currency: PASS
full-input: PASS
special-values: PASS
```

The `reject` helper accepts only `IllegalArgumentException` raised by parser validation rather than using return values to signal errors. This test **intentionally omits** strict grouping; refer to `StrictGroupingDemo` above for policy-based input grammar checks.

**Warning:** in large projects, test helpers should isolate immutable test fixtures and never share formatters across parallel cases. With JUnit 5, write clearly named tests, parameterized tests over locale/kind/input, and report input/code points on failure.

## 17. Designing a More Complete Test Suite for Real Products

A structured test suite:

```text
tests/
  DecimalFormattingTest
  DecimalFullInputParsingTest
  PercentRatioSemanticsTest
  CurrencyCodeAndSymbolTest
  NegativeZeroAndSpecialValuesTest
  StrictGroupingPolicyTest
  UnicodeSeparatorTest
  RoundingAndScaleTest
  LocaleMismatchTest
  JdkLocaleUpgradeRegressionTest
```

This is a **conceptual layout** for a test suite, not files required to be created in this lesson.

Each test case should capture:

```text
field-kind: DECIMAL / PERCENT / CURRENCY
locale-tag: en-US / de-DE / fr-FR / ...
currency-code: USD / EUR / VND / ...
input-text: Unicode string
expected-amount: decimal canonical value
expected-consumed: true/false
expected-valid: true/false
expected-error: parse/type/syntax/domain/currency
rounding-mode: HALF_EVEN / ...
fraction-digits: min/max
runtime/provider metadata: if the snapshot actually depends on it
```

**Measure and log the following on failure:** escaped input, code points, locale tag, format kind, consumed index, error index, `Number` subtype, `BigDecimal` scale, min/max fraction digits, currency code, and provider/JDK version. Never log raw sensitive personal data; test fixtures should use synthetic values.

### Risk-Prioritized Scenarios

- **Orders/taxes/payments:** precision, scale, currency code, and decimal parsing take priority over dot/comma snapshots.
- **Percentage dashboards:** ratio vs. percentage points, rounding, and preserving negative signs.
- **Multilingual locale inputs:** full-input and grouping validation, Unicode spaces.
- **Legacy CSV/imports:** know each file's source locale/format; avoid parsing strings using the viewer's current UI locale.
- **Machine-to-machine APIs:** canonical schemas, independent of `Locale.getDefault()`.
- **JDK/CLDR upgrades:** verify symbol/space/numbering-system changes separately from domain invariants.

## 18. Separating Display Strings from Stored Values

Domain data should look like:

```json
{
  "amount": "1234.50",
  "currency": "USD",
  "ratio": "0.125"
}
```

Where:

- `amount` is a canonical decimal string per contract (or `DECIMAL` column in the DB).
- `currency` is an ISO currency code, not a symbol.
- `ratio` is a 0–1 decimal ratio as defined in the schema.

With this model, the UI can format for `en-US` or `de-DE` without altering the underlying value. When displaying percentages, format the ratio with `getPercentInstance`. When computing money, use `BigDecimal` with explicit rounding/domain policy; never parse display strings back to perform arithmetic.

### The Problem with Storing `format(amount)`

If you store `"1.234,50"` in a DB without a locale, later code might read it with an `en-US` parser, interpret it as `1.234`, and drop the remainder. If you store `"12.5%"` without agreeing on ratio semantics, a consumer might treat `12.5` as a ratio instead of 12.5 percent. If you store `"$1,234.50"` without a currency code, `$` still fails to uniquely identify the currency.

**Solution:** at the input boundary, parse into typed + validated domain objects; at the output boundary, format per locale. Domain and persistence layers never depend on runtime grouping separators, symbols, or whitespace.

## 19. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using only `parse(String)` and checking for no exception | Parser may accept a prefix | `ParsePosition` + compare index with length |
| Treating `getIndex()==length` as strict grammar | `12,34.50` can be fully consumed | Lexical validation per locale policy |
| Using a number formatter for percentages | `12.5%` lacks ratio semantics | `getPercentInstance` with right multiplier |
| Dividing/multiplying by 100 twice | Ratio off by 100× | Store ratio or percentage points explicitly |
| Treating `"$"` as a currency code | `$` spans multiple currencies | Store `Currency`/ISO code |
| Forgetting `setCurrency` when currency differs from locale default | Wrong symbol/unit displayed | Supply currency from domain |
| Converting `BigDecimal` through `double` needlessly | Binary precision loss | Keep decimal exactness |
| Using `BigDecimal.equals` for numeric-only tests | Different scales cause false negatives | `compareTo==0` when comparing value only |
| Assuming `parse(format(x))==x` always holds | Formatting rounding loses digits | Separate domain invariants from display precision |
| Accepting `NaN` for amounts | Special `Number` invalid for money | Check finite/`BigDecimal` type |
| Not testing `-0` | Negative-zero semantics lost | Define explicit policy |
| Normalizing every Unicode space to ASCII | Breaks formatting/no-break semantics | Test per locale and field |
| Parsing `de-DE` input with `en-US` | Wrong value or dropped suffix | Track source locale explicitly |
| Relying on JVM default locale for all users | Output varies by server | Pass locale explicitly |
| Sharing one mutable formatter across threads | Races over currency/fraction settings | Use separate instances or synchronize |
| Fixed snapshots across all JDKs | Tests break on CLDR updates | Track runtime metadata + scoped review |
| Testing only one happy-path number | Misses suffixes, bad grouping, negatives, overflow | Positive/negative/boundary matrix |
| Using locale parsers for canonical APIs | Ambiguous machine-to-machine data | Consistent decimal schema |

## 20. Self-Check Questions

1. **Is `NumberFormat.getNumberInstance` also a percent formatter?** No; use `getPercentInstance` for ratios.
2. **What does `"12.5%"` parse to under a US percent formatter when the domain stores ratios?** `0.125`.
3. **Why can `"1,234.50extra"` return a number?** The parser can consume a prefix; checking only for exceptions is insufficient.
4. **What is the full-input condition?** A valid parsed value of the right type and `ParsePosition.getIndex()==input.length()`.
5. **Does full-input consumption guarantee standard grouping separators?** No; `DecimalFormat` can be lenient with grouping.
6. **Can `"12,34.50"` in `en-US` be parsed into `1234.50`?** Yes, so add grammar validation if strict grouping is required.
7. **Why is `BigDecimal("1.20").equals(BigDecimal("1.2"))` false?** Different scales even though numerically equal.
8. **Does `setParseBigDecimal(true)` convert `NaN` into a `BigDecimal`?** No; `NaN` can return as `Double` and must be handled by domain checks.
9. **Why must `-0` be tested?** Numeric types differ in preserving/dropping negative zero; the domain must define its semantics.
10. **Is `$` enough to identify a currency code?** No, because multiple currencies share that symbol.
11. **Does `NumberFormat.getCurrencyInstance(Locale.GERMANY)` know an order is in USD?** No; set currency from the domain.
12. **Where might `fr-FR` use U+202F?** As the grouping separator in many CLDR/JDK versions.
13. **Should U+202F be converted to U+0020 in all numbers before parsing?** No; define an explicit input contract rather than mutating text arbitrarily.
14. **If a formatter displays only two decimal digits, can parsing recover `1.239` from `1.24`?** No.
15. **Do 0% and 100% need boundary tests?** Yes, along with ratio bounds and policies for negative or >100% values.
16. **Why must currency tests check the currency code separately?** The text parser reads an amount per pattern; symbols can be ambiguous.
17. **Should multi-locale tests rely on `Locale.getDefault()`?** No; pass locales explicitly.
18. **When should you compare literal formatted output?** When testing contracted presentation behavior with runtime/provider pinned.
19. **Is a JSON API sending `"1.234,50"` without a locale safe?** No; use canonical decimals.
20. **Why test parsing unexpected suffixes?** To ensure partially consumed inputs are never accepted.
21. **What is the difference between full parse and domain validation?** Full parse checks characters consumed; domain validation checks business/range rules.
22. **If a test for `"NaN"` returns `Double.NaN`, what should a Money domain do?** Reject it.

## 21. Implementation Checklist

- [ ] Formatters/parsers receive an explicit `Locale`, never an implicit JVM default for user requests.
- [ ] Decimals, percentages, and currencies are tested as **three distinct categories**.
- [ ] Money domain uses `BigDecimal` plus currency code; ratio domain has explicit semantics.
- [ ] Format, parse, full-input consumption, and business/lexical validation are all tested.
- [ ] `ParsePosition` starts at 0; ending index is compared against the entire input length.
- [ ] Value types are checked; `NaN`/infinity are blocked from domains that forbid them.
- [ ] Negative zero, sign, min/max, precision, scale, and rounding are tested.
- [ ] Locale mismatches and swapped `,`/`.` roles are tested.
- [ ] Garbage suffixes, empty strings, invalid grouping, wrong currency symbols, and percents missing `%` are tested.
- [ ] Unicode whitespace U+0020/U+00A0/U+202F and supported numbering systems are tested.
- [ ] Full consumption is never assumed to guarantee valid grouping.
- [ ] `parse(format(x)) == x` is not asserted when the formatter rounds or drops precision.
- [ ] Localized display strings are never persisted as the source of truth.
- [ ] Presentation output tests pin JDK/CLDR/provider when asserting exact literals.
- [ ] Mutable formatters are never shared unprotected across threads.
- [ ] QA runs on production's runtime/locale provider with at least one realistic legacy input dataset.

## References

- [Oracle Java SE 17 — NumberFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html): decimal, integer, currency, and percent factories; locale parsing and `ParsePosition`.
- [Oracle Java SE 17 — DecimalFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormat.html): patterns, rounding, `setParseBigDecimal`, prefix parsing, special numbers.
- [Oracle Java SE 17 — DecimalFormatSymbols](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormatSymbols.html): decimal/grouping marks, currency, and numbering symbols.
- [Oracle Java SE 17 — ParsePosition](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/ParsePosition.html): parse success/failure position tracking.
- [Oracle Java SE 17 — BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): decimal scale/precision and `equals` vs. `compareTo`.
- [Oracle Java SE 17 — Currency](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Currency.html): currency codes and locale symbols.
- [Oracle Java SE 17 — Locale](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html): locale tags and `Category.FORMAT`.
- [Unicode CLDR](https://cldr.unicode.org/): data on separators, number patterns, currency symbols, and per-version changes.
