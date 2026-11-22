# DecimalFormat: Positive/Negative Subpatterns, Prefixes, and Suffixes in Java

## 1. Objectives and context

`java.text.DecimalFormat` is a number formatting/parsing class customizable via **patterns** and `Locale`-specific symbols. When an application needs to display negative numbers in accounting parentheses, append a unit word after a number, or place different labels before positive and negative values, developers must master **positive/negative subpatterns** and **prefixes/suffixes**.

For example, the same magnitude 1,234.5 can be represented by convention as:

- Positive number: `1,234.50`
- Negative number: `-1,234.50`
- Accounting-style negative number: `(1,234.50)`
- With labels: `Amount: 1,234.5 units` or `Loss: 1,234.5 units`

In the examples above, the comma, period, and grouping characters depend on the chosen symbol set; the text `Amount`, `Loss`, and `units` are **application-defined prefixes/suffixes**, not the number's own value.

After this lesson, you will be able to:

1. Read and write the `positiveSubpattern;negativeSubpattern` syntax.
2. Understand the difference between syntax symbols `0`, `#`, `,`, `.`, `;`, `'` and prefix/suffix literals.
3. Use negative subpatterns to show a minus sign or parentheses, and understand behavior when no negative subpattern is declared.
4. Distinguish **digit patterns** from **prefixes/suffixes**, avoiding bugs when configuring positive and negative numbers with different precisions.
5. Use `DecimalFormatSymbols`/`Locale`, format currency/percent, and use setter APIs in a controlled manner.
6. Handle zero, negative zero, rounding, parsing, sharing formatters across threads, and testing.

## 2. General pattern structure

A typical `DecimalFormat` pattern has the structure:

```text
positiveSubpattern[;negativeSubpattern]
```

Each subpattern can contain three regions:

```text
[prefix] number-pattern [suffix]
```

Example:

```text
#,##0.00;(#,##0.00)
│           │
│           └── negative: prefix "("; number part "#,##0.00"; suffix ")"
└────────────── positive: empty prefix/suffix; number part "#,##0.00"
```

With `Locale.US` symbols:

| Value | Pattern | Output |
| ---: | --- | --- |
| `1234.5` | `#,##0.00` | `1,234.50` |
| `-1234.5` | `#,##0.00` | `-1,234.50` |
| `1234.5` | `#,##0.00;(#,##0.00)` | `1,234.50` |
| `-1234.5` | `#,##0.00;(#,##0.00)` | `(1,234.50)` |
| `0` | `#,##0.00;(#,##0.00)` | `0.00` |

**Only one subpattern?** If no negative subpattern is declared, the formatter derives the negative style from the positive pattern, typically prepending the minus sign from `DecimalFormatSymbols` before the positive branch's prefix. You do not need to write a negative subpattern manually just to get a standard minus sign.

**Two subpatterns?** The semicolon `;` separates positive and negative subpatterns; this character is not printed in the output. If you want `;` as literal display text in a prefix/suffix, quote it as a literal.

### A common misconception: the digit pattern in the negative branch

In `DecimalFormat`, rules for **digit counts, grouping, and precision** are taken from the **positive branch**. The numeric part in the negative subpattern is parsed structurally, but **you cannot use the negative branch to get a different number of decimal places than the positive branch**. The negative branch primarily determines the prefix/suffix for negative values.

Example:

```java
DecimalFormat df = new DecimalFormat(
        "0.00;(0)",
        DecimalFormatSymbols.getInstance(Locale.US));

System.out.println(df.format(-12.3)); // (12.30)
```

Even though the numeric part in the negative branch says `0`, the result still has two decimal places according to the positive part `0.00`. If a product truly needs different digit rules for positive and negative numbers, choose **two formatters** or configure separately in code based on business logic rather than expecting two subpatterns to solve it.

## 3. Important symbols in the numeric part

| Symbol | Role in pattern | Remember |
| --- | --- | --- |
| `0` | Required digit; padded with `0` if missing. | `0.00` always shows two fractional digits. |
| `#` | Optional digit; does not add unnecessary zeros. | `#,##0` still has at least one integer digit because of `0`. |
| `.` | Integer/fraction separator symbol **in non-localized patterns**. | Display character depends on `DecimalFormatSymbols`. |
| `,` | Grouping symbol in pattern. | Position and displayed character depend on pattern + locale. |
| `;` | Separates positive/negative subpatterns. | Not an actual data separator. |
| `'... '` | Quotes a literal in the pattern. | Turns special symbols into displayed text. |
| `%` | Represents percent and applies a multiplier of 100. | Not merely the character "%". |
| `‰` | Represents per-mille and applies a multiplier of 1000. | Not equivalent to percent. |
| `¤` | Currency symbol placeholder; `¤¤` typically represents ISO currency code. | Actual currency must come from transaction data. |
| `E` | Exponent notation symbol when used in scientific syntax. | Not a literal when inside the number skeleton. |

The symbols above belong to **standard pattern syntax**, typically used with `applyPattern(...)` or the `DecimalFormat(pattern, symbols)` constructor. Display of separators, minus signs, % symbols, and currencies can vary between locales.

For instance, the pattern `#,##0.00` with US symbols prints `1,234.50`, whereas in another locale the decimal and grouping separators may swap positions. Do not infer from `.` and `,` in the pattern that the output data must use those exact characters.

## 4. Positive and negative subpatterns

### 4.1. Default negative formatting

```java
DecimalFormat df = new DecimalFormat(
        "#,##0.00",
        DecimalFormatSymbols.getInstance(Locale.US));

System.out.println(df.format(-1234.5)); // -1,234.50
```

Because no negative branch is provided, `DecimalFormat` formats the number using the positive branch and adds the symbol set's default minus sign. This is usually sufficient for quantities, ordinary values, or technical labels.

### 4.2. Negatives in parentheses by accounting convention

```java
DecimalFormat df = new DecimalFormat(
        "#,##0.00;(#,##0.00)",
        DecimalFormatSymbols.getInstance(Locale.US));

System.out.println(df.format(1234.5));  // 1,234.50
System.out.println(df.format(-1234.5)); // (1,234.50)
```

The `(` and `)` characters are the prefix/suffix of the negative branch. There is no `-` minus sign in the output because we explicitly replaced how the negative sign is displayed.

This is only a **presentation convention**. The sign/magnitude of the number does not change: `df.format(-1234.5)` still formats a negative value; only the displayed string differs.

### 4.3. Distinct prefix/suffix for each sign

You can place text before and after the numeric region:

```text
'Amount: '#,##0.0' units';'Loss: '#,##0.0' units'
```

Under `Locale.US`:

- `1234.5` → `Amount: 1,234.5 units`
- `-1234.5` → `Loss: 1,234.5 units`

Here, `Amount: ` and `Loss: ` are prefixes; ` units` is the suffix. Use quoted literals so the parser distinguishes text from special pattern symbols.

Do not use manual concatenation like `"Loss: " + format.format(-number)` to represent all negative forms: an application may need accounting parentheses, reordered words, or another language using different phrasing. However, **DecimalFormat is not a full-sentence translation system**; for grammatically rich text, use `ResourceBundle`/`MessageFormat` for the message and `DecimalFormat` strictly for formatting the number.

## 5. Reading and modifying prefixes/suffixes via API

`DecimalFormat` provides corresponding getters/setters:

| Getter | Setter | Function |
| --- | --- | --- |
| `getPositivePrefix()` | `setPositivePrefix(String)` | String before positive numbers. |
| `getPositiveSuffix()` | `setPositiveSuffix(String)` | String after positive numbers. |
| `getNegativePrefix()` | `setNegativePrefix(String)` | String before negative numbers. |
| `getNegativeSuffix()` | `setNegativeSuffix(String)` | String after negative numbers. |

Illustrative example:

```java
DecimalFormat df = new DecimalFormat(
        "#,##0.00",
        DecimalFormatSymbols.getInstance(Locale.US));
df.setPositivePrefix("+");
df.setPositiveSuffix(" units");
df.setNegativePrefix("(");
df.setNegativeSuffix(" units)");

System.out.println(df.format(8));  // +8.00 units
System.out.println(df.format(-8)); // (8.00 units)
```

This snippet belongs in a Java method with proper imports; it demonstrates changing **affix strings**, without altering the number itself. The setters take literal strings, without requiring the caller to wrap strings in quote marks in Java as in patterns.

**Changing patterns after setters:** `applyPattern(...)` re-parses the pattern and can overwrite previous prefixes/suffixes. Establish a clear configuration order; if using a pattern as the base, apply the pattern first and then override affixes as needed.

**Saving patterns:** `toPattern()` returns a pattern representation; if you have customized symbols/affixes via setters, do not take the string from `toPattern()` and assume it captures all semantics of custom mutations. Test the formatter against important real values.

**Note on distinguishability:** positive and negative subpatterns should not have identical prefixes/suffixes that make the parser unable to distinguish the sign. When parsing numbers from strings, design unambiguous syntax and test both positive and negative parsing.

## 6. Literals, single quotes, and special characters

In `DecimalFormat` syntax, **quoting with single quotes** allows turning symbols that have special meaning into literal display text. For example:

```text
'Total: '#,##0.00' USD'
```

This renders a number with prefix `Total: ` and suffix ` USD`, without multiplying or altering the numeric value. If you need to display a **single quote** inside a literal, write two single quotes `''` per `DecimalFormat` quoting rules.

Symbols like `%` and `¤` must be distinguished carefully:

- **Unquoted `%` in a pattern** → percentage formatting, multiplying the numeric value by 100 before display.
- **Quoted `'%'`** → renders the percent character as a literal; it **does not multiply by 100**. Which one is right depends on the source value's unit.
- **Using `¤`** → currency placeholder determined by `DecimalFormatSymbols` and `Currency`.
- **Using `'USD '` or `' VND'`** → fixed literal text; it does not guarantee the underlying currency unit of the data.

If a user message needs phrasing like "Negative balance", "Refund", or "Credit", let the localization layer choose the appropriate sentence. Prefixes/suffixes should serve cases tightly coupled to **numeric representation**, avoiding stuffing entire sentences or grammatical structures into number patterns.

### Literal semicolons

An unquoted `;` separates two subpatterns; if you want a display prefix containing `;`, use quoting syntax so the parser treats it as literal text instead of unintentionally starting a negative branch.

### Locale-specific minus signs

The minus sign in a string can be supplied by `DecimalFormatSymbols.getMinusSign()`. Do not assume every locale uses ASCII `-`, and do not manually replace characters on the formatted string afterward. If the product requires a specific minus sign, configure symbols or prefix/negative pattern intentionally and test it.

## 7. Percent, per-mille, and currency in prefixes/suffixes

### 7.1. Percent and multiplier

`DecimalFormat` treats `%` in a pattern as a special symbol: it places the percent sign in the affix **and multiplies the value by 100**.

```java
DecimalFormat ratio = new DecimalFormat(
        "0.0%;(0.0%)",
        DecimalFormatSymbols.getInstance(Locale.US));

System.out.println(ratio.format(0.125));  // 12.5%
System.out.println(ratio.format(-0.125)); // (12.5%)
```

If business data already stores `12.5` meaning "12.5 percent", using a percent pattern without scaling the unit yields `1,250.0%`. Standardize whether inputs are fractions (0.125) or already-scaled percentages (12.5).

Similarly, the per-mille symbol `‰` applies a multiplier of 1000. When you only want to append a literal symbol without scaling the number, quote it properly.

### 7.2. Currency is formatting only

The pattern:

```text
¤#,##0.00;(¤#,##0.00)
```

can display a positive/negative monetary amount, with the negative branch in parentheses. The `¤` symbol is replaced with the currency symbol per configuration; `¤¤` can render the ISO 4217 code such as `USD`. Different locales and JDK versions have different currency data/symbols.

When a transaction's currency differs from the locale's usual currency, set the currency **according to business data**:

```java
Locale locale = Locale.US;
DecimalFormatSymbols symbols =
        DecimalFormatSymbols.getInstance(locale);
DecimalFormat money = new DecimalFormat(
        "¤#,##0.00;(¤#,##0.00)", symbols);
money.setCurrency(Currency.getInstance("EUR"));
```

This snippet belongs in a Java method and requires importing `java.text.DecimalFormat`, `java.text.DecimalFormatSymbols`, `java.util.Locale`, and `java.util.Currency`. Check the actual displayed currency symbol if the application relies on a specific label.

**`setCurrency(...)` does not convert exchange rates.** It changes the metadata used to format the monetary unit, without multiplying/dividing amounts to convert EUR to USD or vice versa. Conversion must live in the business layer with an explicitly defined exchange rate.

### 7.3. When to use literal "USD" instead of a currency placeholder?

If a pattern has `' USD'`, that is simply fixed literal text that always appears. It may fit a USD-only fixed report, but will be wrong if reused for EUR transactions. For multi-currency payment software, pass currency dynamically from data rather than hardcoding unit metadata into pattern literals.

## 8. Complete Java 17+ example: formatting positives, negatives, affixes, and suffixes

Create the file **`DecimalFormatAffixDemo.java`** with the following content. The examples use `Locale.US` symbols so numeric outputs are predictable without changing the JVM-wide default.

```java
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class DecimalFormatAffixDemo {
    public static void main(String[] args) {
        DecimalFormatSymbols symbols =
                DecimalFormatSymbols.getInstance(Locale.US);

        DecimalFormat accounting = new DecimalFormat(
                "#,##0.00;(#,##0.00)", symbols);

        System.out.println("positive="
                + accounting.format(1234.5));
        System.out.println("negative="
                + accounting.format(-1234.5));
        System.out.println("zero="
                + accounting.format(0));
        System.out.println("negativeZero="
                + accounting.format(-0.0));
        System.out.println("negativePrefix="
                + accounting.getNegativePrefix());
        System.out.println("negativeSuffix="
                + accounting.getNegativeSuffix());

        DecimalFormat ordinary = new DecimalFormat(
                "#,##0.00", symbols);
        System.out.println("autoNegative="
                + ordinary.format(-1234.5));

        DecimalFormat labeled = new DecimalFormat(
                "'Amount: '#,##0.0' units';"
                + "'Loss: '#,##0.0' units'",
                symbols);
        System.out.println("labelPositive="
                + labeled.format(1234.5));
        System.out.println("labelNegative="
                + labeled.format(-1234.5));

        DecimalFormat ratio = new DecimalFormat(
                "0.0%;(0.0%)", symbols);
        System.out.println("percentPositive="
                + ratio.format(0.125));
        System.out.println("percentNegative="
                + ratio.format(-0.125));

        // The numeric part of the negative branch does not change
        // the precision of the positive branch "0.00".
        DecimalFormat sameDigits = new DecimalFormat(
                "0.00;(0)", symbols);
        System.out.println("negativeDigits="
                + sameDigits.format(-12.3));
    }
}
```

Compile and run with JDK 17 or newer in the directory containing the file:

```bash
javac -encoding UTF-8 DecimalFormatAffixDemo.java
java DecimalFormatAffixDemo
```

**Exact stdout:**

```text
positive=1,234.50
negative=(1,234.50)
zero=0.00
negativeZero=(0.00)
negativePrefix=(
negativeSuffix=)
autoNegative=-1,234.50
labelPositive=Amount: 1,234.5 units
labelNegative=Loss: 1,234.5 units
percentPositive=12.5%
percentNegative=(12.5%)
negativeDigits=(12.30)
```

### Reading the output step by step

1. `positive` and `negative` are formatted with the same two decimal places and grouping. The negative branch uses `(` and `)` instead of a minus sign.
2. `zero` uses the positive branch rule: `0.00`. `DecimalFormat` has no third "zero subpattern" in standard positive/negative syntax.
3. `negativeZero` outputs `(0.00)` because a `double` can carry a negative sign even when its magnitude is 0. This is **negative zero**; see section 9.
4. `getNegativePrefix()` and `getNegativeSuffix()` reflect the actual affixes parsed from the pattern.
5. `ordinary` does not declare a negative branch, so it yields `autoNegative=-1,234.50`.
6. `labeled` uses prefix labels `Amount: ` / `Loss: ` and suffix ` units` for the two signs.
7. `ratio` multiplies the value by 100 and adds the percent sign; the negative side again uses parentheses.
8. `negativeDigits=(12.30)` proves that digit rules are taken from the positive branch `0.00`, even though the negative branch contains `0`.

The verification values are numeric formatting examples; do not treat the words "Amount"/"Loss" as automatic translations for all locales.

## 9. Zero, negative zero, rounding, and special values

### 9.1. Regular zero

The pattern `#,##0.00;(#,##0.00)` does not define a separate branch for zero. For non-negative zero, the formatter uses the positive subpattern and prints `0.00`. If an application wants to display zero as a dash or the word "None", handle that with a separate policy in the presentation or business layer; do not guess that a third `;zeroPattern` is valid `DecimalFormat` syntax.

### 9.2. Negative zero

Under IEEE 754, `double` and `float` can hold `-0.0`, which differs in sign from `+0.0`. `DecimalFormat` preserves the sign when formatting, so the negative branch can be selected for `-0.0`, causing the application to print `(0.00)`.

If business rules require both `-0.0` and `0.0` to output `0.00`, normalize the input **according to the business contract** before formatting; note that normalization can discard sign information that scientific calculations may need to preserve.

Similarly, a very small negative value may round to zero while still carrying a negative sign in the display string. Test rounding thresholds if negative values in parentheses carry accounting significance.

### 9.3. RoundingMode and decimal places

`DecimalFormat` can round when fewer display digits are requested than the source has. Displaying `1.234` as `1.23` does not mean the original number was modified. If the result is currency or high-precision data, use `BigDecimal` for the input with a contract-appropriate `RoundingMode`, for example:

```java
DecimalFormat df = new DecimalFormat(
        "#,##0.00;(#,##0.00)",
        DecimalFormatSymbols.getInstance(Locale.US));
df.setRoundingMode(RoundingMode.HALF_UP);
String view = df.format(new BigDecimal("-12.345"));
```

This snippet belongs in a Java method with imports `java.math.BigDecimal`, `java.math.RoundingMode`. `setRoundingMode(...)` only controls the **rounding rule inside the formatter**; it does not automatically establish valid financial rules for every currency and scenario.

### 9.4. Infinity and NaN

`Double.NaN` or infinity values have special display forms governed by `DecimalFormatSymbols`. Do not expect them to be handled like ordinary finite decimal numbers or to follow all precision and grouping rules. Inputs for transactions, payroll, or invoices should be validated and have an explicit policy for non-finite numbers.

## 10. Parsing formatted numbers: important caveats

`DecimalFormat` can also parse strings via `parse(...)`. For example, the accounting formatter `#,##0.00;(#,##0.00)` can recognize a negative value from parentheses if the pattern and symbols match.

However, formatting and parsing are not always strictly symmetric in every case:

- **Fractional digits that were rounded off** in the display string cannot automatically recover their original precision.
- A pattern that distinguishes positive/negative solely by affixes must ensure **the affixes are sufficiently distinct**, otherwise the parser cannot determine the sign.
- `parse(String)` can accept a valid prefix of the string; when validating user input, use `ParsePosition` to verify **the entire** string was consumed.
- `parseBigDecimal` on `DecimalFormat` is useful when needing more accurate decimal values for input, but it does not turn the parser into a business validator or a currency converter.
- Separators, minus signs, suffixes, and currency symbols must match the parser's `DecimalFormatSymbols`/pattern.
- Do not use formatted output as a "numeric identifier" or for API/database serialization. Display formats can change across locales, product requirements, and locale data versions.

Example of verifying full string consumption (illustrative code inside a Java method):

```java
DecimalFormat df = new DecimalFormat(
        "#,##0.00;(#,##0.00)",
        DecimalFormatSymbols.getInstance(Locale.US));

ParsePosition pos = new ParsePosition(0);
String input = "(1,234.50)";
Number value = df.parse(input, pos);

boolean valid = value != null
        && pos.getIndex() == input.length();
```

Requires importing `java.text.ParsePosition`. The `valid` condition here only checks that the parser read the whole string; checks such as value bounds, business type, precision, and currency must still be performed separately.

## 11. Locale and DecimalFormatSymbols: patterns are not fixed strings

`DecimalFormatSymbols` provides the actual symbols for digits, grouping separators, decimal points, minus signs, percentages, currency, and special values. When predictable output is desired, create symbols from an explicit locale:

```java
Locale locale = Locale.US;
DecimalFormatSymbols symbols =
        DecimalFormatSymbols.getInstance(locale);
DecimalFormat df = new DecimalFormat("#,##0.00", symbols);
```

These are illustrative statements inside a Java method.

**`applyPattern(...)` and `applyLocalizedPattern(...)` are not the same:**

- `applyPattern(...)` reads standard pattern syntax (`.`, `,`, `#`, `0`...) and then uses symbols for display.
- `applyLocalizedPattern(...)` reads a pattern with symbols already localized according to `DecimalFormatSymbols`. Use it only when the input is genuinely a localized pattern; avoid switching arbitrarily between the two forms.

For example, a standard pattern `#,##0.00` should not be manually translated by replacing `.` with `,` and passed to `applyPattern(...)` just because a locale uses a decimal comma. Instead, configure symbols/locale. The pattern defines **formatting structure**; symbols define **display characters**.

### Locale data is not transaction currency

Locale determines default symbols/formats, while currency values, required decimal digits, parentheses vs. minus signs for negatives, and rounding rules are usually product requirements. You may need to select `Currency` separately and test each market. Never infer a currency code from nationality or solely from `getCountry()` in user profile data.

## 12. Thread safety and reusing formatters

`DecimalFormat` is a **mutable** object and is not guaranteed thread-safe when used concurrently across multiple threads. Methods such as `applyPattern(...)`, `setPositivePrefix(...)`, `setRoundingMode(...)`, and other setters can mutate configuration while another request is using it.

Practical options:

1. **Create a formatter per call/request** when requirements are simple and the cost is acceptable.
2. **Create a template formatter and `clone()` it per thread/use** when configuration is heavy and cloning has been tested.
3. **Synchronize with proper scope** if an instance must be shared; avoid ineffective local locks across threads.
4. **Do not use a mutable static DecimalFormat** and update its prefix/suffix per request or locale.

Even if only calling `format(...)` from multiple threads, `DecimalFormat`'s contract does not guarantee safe sharing; do not rely on luck from single-threaded tests.

## 13. Common mistakes and how to avoid them

| Mistake | Consequence | How to handle |
| --- | --- | --- |
| Writing `positive;negative` to give negatives a different digit count | The negative branch's numeric pattern does not control separate precision. | Use two formatters when different digit policies are required. |
| Omitting the negative subpattern yet expecting parentheses | Default uses the ordinary minus sign. | Declare negative prefix/suffix, e.g. `(#,##0.00)`. |
| Manually prepending a minus sign after `format` | Breaks easily with locales, negative zero, and existing affixes. | Set the pattern/negative prefix properly from the start. |
| Forgetting to quote `;`, `%`, or special literals | Parser treats them as syntax, changing branches or multipliers. | Use proper quoting or setter APIs for literal strings. |
| Using `0.0%` with values already multiplied by 100 | Result is off by a factor of 100. | Determine the ratio unit before formatting. |
| Using fixed `'USD'` across multiple currencies | Wrong currency label when transactions change units. | Supply `Currency` from business logic. |
| Treating `¤` as an exchange-rate converter | Only displays currency, does not convert values. | Separate formatting from currency conversion. |
| Forgetting to test `-0.0` | Output can become `(0.00)`. | Define a policy for negative zero. |
| Setting negative branch via setters then calling `applyPattern` | Pattern can overwrite earlier affix configuration. | Configure in consistent order and test final output. |
| Parsing strings with suffixes without checking remainder | Accepts invalid input when parser stops partway. | Use `ParsePosition` and check consumed length. |
| Sharing a mutable static formatter across threads | Risk of cross-request state corruption and irreproducible results. | Clone or instantiate per request. |
| Testing only positive numbers | Misses negative branches, negative zero, zero, rounding, and affixes. | Build a test matrix covering all signs and boundaries. |

## 14. Practice exercises

**Exercise 1 — Accounting negative pattern:** use `#,##0.00;(#,##0.00)` to print `1234.5`, `-1234.5`, `0`, `-0.0`. Explain why `-0.0` can output parentheses, and where to handle it if the product wants otherwise.

**Exercise 2 — Prefix/suffix:** design a format labeled `Credit: ` for positives, `Debit: ` for negatives, with suffix ` units`. Implement it once using pattern quoted literals and once using setters. Inspect `getPositivePrefix()`/`getNegativeSuffix()`, then call `applyPattern(...)` to observe the configuration being overwritten.

**Exercise 3 — Negative branch precision:** try `0.00;(0)` with `-12.3`. Explain why it does not output `(12)`. Design two separate formatters if business requirements truly want positives shown with two fractional digits and negatives with none.

**Exercise 4 — Percent and currency:** try `0.0%;(0.0%)` with `0.125` and `-0.125`; compare with a pattern having a literal `'%'`. Next, distinguish `¤`, `¤¤`, and `'USD'` when locale/`Currency` changes. Do not perform exchange-rate conversion in the formatter.

**Exercise 5 — Accounting parse:** use `parse(String, ParsePosition)` with `(1,234.50)`, `1,234.50`, a string with trailing characters, and a string with an invalid prefix. Accept input only when parsing succeeds **and** consumes the entire string. Add range validation.

**Exercise 6 — Two locales:** create a `#,##0.00;(#,##0.00)` formatter with `Locale.US` and another supported product locale. Observe how decimal/grouping symbols change while the pattern structure remains the same; explain when to use `applyLocalizedPattern`.

### Completion checklist

- [ ] Can read `positiveSubpattern;negativeSubpattern` and distinguish `;` from decimal separators.
- [ ] Understands that negative subpatterns change **prefixes/suffixes**, not negative-specific precision.
- [ ] Knows how to use `get/setPositivePrefix`, `get/setNegativeSuffix`, and quoted literals.
- [ ] Distinguishes percent multipliers, per-mille, and currency symbols from literal text.
- [ ] Properly tests `0`, `-0.0`, positive/negative numbers, rounding, and parsing.
- [ ] Passes `Locale`/`DecimalFormatSymbols` explicitly and manages currency via business data.
- [ ] Does not share mutable `DecimalFormat` instances across threads without safety mechanisms.

**Takeaway:** `DecimalFormat` patterns determine how **numeric values and affixes** are rendered. Do not use the negative branch to change precision, do not mistake currency symbols for currency conversion, and do not turn number formatting into a dumping ground for full translation or business logic.
