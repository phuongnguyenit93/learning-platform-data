# Distinguishing Display Strings from Numeric Representations for Storage or Exchange in Java

## Goal

A numeric value can be displayed across many languages and regions while its **mathematical value does not change**. For example, the same number twelve thousand three hundred forty-five point six seven eight can be presented as `12,345.678` or `12.345,678`. These strings serve **human readers**, not as a stable data format for writing to a database or transmitting between systems.

This lesson focuses on the boundary between two needs:

- **Presentation:** selecting decimal separators, grouping separators, digits, decimal places, percent/currency symbols, and rounding rules according to `Locale`.
- **Storage or exchange:** keeping numbers in a numeric data type or a text form with a **fixed grammar**, independent of the machine's or user's locale and with a clear precision contract.

After this lesson, you will be able to use `NumberFormat` and `DecimalFormat` in the right place, choose `BigDecimal`/`toPlainString()` when exact decimals are required, recognize the risks of parsing formatted strings, and design stable data contracts for JSON, CSV, or databases.

## 1. One Number, Many Written Forms for Humans

Consider the mathematical value `12345.6789`. A program might display approximations:

| Context | Example string | Meaning of separators |
| --- | --- | --- |
| English (United States), 3 decimal places | `12,345.679` | `,` groups; `.` is the decimal point |
| German (Germany), 3 decimal places | `12.345,679` | `.` groups; `,` is the decimal point |
| Ungrouped ASCII decimal representation | `12345.6789` | `.` is the decimal point per data contract |

The two display strings in the table were **rounded** to three digits after the decimal point: they no longer retain enough information to reconstruct `12345.6789` exactly. The last string represents all the original digits that the example requires preserving.

In practice, display output can also differ in grouping characters (regular space, non-breaking space, narrow non-breaking space), digit sets, negative signs, and currency conventions. That is why a program must not define its data format as "store the exact string the user sees on screen."

**Distinguish three entities:**

1. **Numeric value:** e.g., a `BigDecimal("12345.6789")` object.
2. **Display string:** the result of `NumberFormat.format(value)` for a specific locale.
3. **Exchange representation:** e.g., a JSON number field or a decimal string with `.`, no grouping, and an accompanying schema specification.

Both display strings and exchange representations are text, yet they **do not share the same contract**. The difference lies in the intended consumer and reliable parsability, not in both having the Java type `String`.

## 2. NumberFormat Belongs to the Presentation Layer

`java.text.NumberFormat` provides `Locale`-based formatters:

```java
import java.text.NumberFormat;
import java.util.Locale;

NumberFormat number = NumberFormat.getNumberInstance(Locale.GERMANY);
NumberFormat percent = NumberFormat.getPercentInstance(Locale.GERMANY);
NumberFormat currency = NumberFormat.getCurrencyInstance(Locale.GERMANY);
```

This is an illustrative snippet inside a method. The formatters serve different roles:

- `getNumberInstance(locale)`: represents decimal numbers according to the locale's conventions.
- `getIntegerInstance(locale)`: formats integer style according to the locale's conventions.
- `getPercentInstance(locale)`: formats percentage ratios; a value of `0.25` may display as 25%.
- `getCurrencyInstance(locale)`: formats using the default currency conventions tied to the locale, if suitable data is available.

Formatters can affect grouping separators, decimal separators, digits, negative-sign styles, fractional digit counts, and **rounding**. That behavior is desirable in the UI, but dangerous if the output is saved as source data.

Example:

```java
BigDecimal amount = new BigDecimal("12345.6789");
NumberFormat german = NumberFormat.getNumberInstance(Locale.GERMANY);
german.setMaximumFractionDigits(3);
String display = german.format(amount);
```

This is an illustrative snippet inside a method, with `import java.math.BigDecimal;` and `import java.util.Locale;`. The string `display` is produced for **human reading** in the German locale, not as an internal protocol for another service to parse using its defaults.

### Do Not Use the Default Locale Unintentionally

These two calls:

```java
NumberFormat.getNumberInstance()
NumberFormat.getNumberInstance(Locale.GERMANY)
```

are not equivalent in stability. The first uses the JVM's formatting default (category `FORMAT`); settings can differ across developer machines, CI, and production. The second states the locale explicitly.

In multi-user applications, obtain the locale from the request context and **pass it explicitly**. Never change `Locale.setDefault(...)` per user: the default is shared JVM-wide state and can alter results for other requests.

## 3. Number Formatting Is Not a Value-Preserving Process

Some systems only want to display at most two decimal places. When the formatter rounds:

```text
Value:           12345.6789
Shown 2 digits:  12,345.68      (en-US illustration)
```

The trailing `89` information is lost in the display string. If you parse `12,345.68`, you get the number representing the **rounded value**, unable to recover the exact original number.

Rounding is not the only cause of data loss:

- Percentage formatting multiplies the value by 100 and adds a `%` symbol, e.g., `0.25` ↔ `25%`. Parsing with a mismatched formatter type can be off by a factor of 100.
- Currency formatting may round to the currency unit's default fractional digits.
- A formatter may omit trailing decimal zeros not needed for display, losing **scale** information from `BigDecimal`.
- Strings may use non-ASCII digits or grouping separators depending on the locale.
- Two distinct numbers can yield the same output if rounded to low precision.

Therefore, **do not use `format` followed by `parse` as an intermediate storage mechanism**. Formatting makes messages readable; original data must be preserved separately.

### The Currency Case

The pair `amount` and `currency` is business data. Locale may govern **how it is displayed**, yet does not always dictate the **transaction currency**. Someone choosing a Vietnamese UI may pay in USD or EUR.

Do not store just `"$1,234.50"`: the `$` symbol can correspond to different currencies, grouping and decimal marks depend on context, and displayed decimal places do not capture full billing rules. Store the **exact numeric value + ISO 4217 currency code**, and apply business rounding rules explicitly.

## 4. Stable Formats Must Have an Explicit Grammar

For numeric exchange fields, a contract typically needs to specify:

- **Data type:** integer or decimal, signed or unsigned, whether scientific notation is supported.
- **Character set:** ASCII digits `0–9`, minus sign `-`, decimal point `.`, with no grouping separators.
- **Scale/precision/range:** digit limits, value bounds, whether trailing fractional zeros are preserved.
- **Unit semantics:** e.g., monetary total with a separate currency code, weight in kilograms, ratio `0.25` vs. percentage `25`.
- **Representation of missing values:** schema `null` or omitted field; never write the literal `"null"` as a number.
- **Parsing and error rules:** malformed input must be rejected, not guessed using the system locale.

A simple decimal representation under contract:

```text
-12345.6789
0
0.125
1000
```

These **have no grouping separators**; the decimal mark is always `.`. This example illustrates one text decimal exchange profile, without claiming it is the sole format for all protocols.

JSON allows numbers with a fixed grammar (`.` decimal point, optional exponent); JSON **does not allow** locale grouping separators, nor does it allow `NaN` or `Infinity` as numbers. A given schema may choose a JSON number or a JSON string containing a canonical decimal. They differ in data type and client compatibility.

### JSON Number vs. Exact Decimal String

These two examples carry different contracts:

```json
{"quantity": 12345.6789}
```

```json
{"amount": "12345.6789", "currency": "EUR"}
```

In the first example, `quantity` is a **JSON number**. JSON syntax itself does not guarantee every client preserves full numeric precision, because some clients decode all JSON numbers as IEEE 754 binary64. In the second example, `amount` is a **JSON string** under a schema specifying a canonical decimal string; clients must parse it into an appropriate decimal type rather than treating it casually as a UI string.

You cannot say "all numbers must be sent as Strings" or "all numbers are always sent as JSON numbers." The decision depends on semantics, value range, precision, and sender/receiver capabilities. For money or decimals requiring absolute precision, some APIs choose a decimal string plus currency; others use an integer count of smallest units (such as cents) with the unit clearly documented. Both are valid when the **contract is exact and unambiguous**.

## 5. BigDecimal and toPlainString for Decimal Data

`java.math.BigDecimal` stores decimals with precision governed by digits and scale, making it highly useful for currency, quantities, and exact decimal data.

Construct from a validated decimal string:

```java
import java.math.BigDecimal;

BigDecimal value = new BigDecimal("12345.6789");
String wire = value.toPlainString();
System.out.println(wire);
```

This is an illustrative snippet inside a method. Stdout:

```text
12345.6789
```

`toPlainString()` formats the number in standard form without scientific notation, using an ASCII `.` decimal point and no locale grouping. It is suitable as **part** of a string-based decimal exchange contract if the receiver accepts that exact grammar and documented bounds.

Notes:

1. `toPlainString()` **does not enforce** your application's length limits, digit counts, scale, or range bounds.
2. Numerically equal values with different scales produce different strings, e.g., `"1.0"` and `"1.00"`. Decide whether to preserve scale per business rules.
3. `BigDecimal.toString()` is also well-defined, yet may use scientific notation; `toPlainString()` is the choice when the schema forbids exponents.
4. A `BigDecimal` can have a negative scale; conversions between forms must be well understood if clients require preserving the original representation.
5. `BigDecimal` does not replace specifying currency, unit, and rounding policy.

### Avoid Constructing BigDecimal Directly from double When Decimal Exactness Matters

`double` uses binary representation and cannot represent many familiar decimal fractions such as `0.1` exactly. Compare:

```java
BigDecimal a = new BigDecimal("0.1");
BigDecimal b = BigDecimal.valueOf(0.1);
BigDecimal c = new BigDecimal(0.1);

System.out.println(a.toPlainString());
System.out.println(b.toPlainString());
System.out.println(c.toPlainString());
```

Inside a method importing `BigDecimal`, output:

```text
0.1
0.1
0.1000000000000000055511151231257827021181583404541015625
```

`new BigDecimal("0.1")` preserves the entered decimal string; `BigDecimal.valueOf(0.1)` uses the decimal representation via `Double.toString` of the `double`; whereas `new BigDecimal(0.1)` reflects the exact binary value of the `double`, producing the long tail.

This does not mean `BigDecimal` is mandatory everywhere. For measurements/graphics/statistics that tolerate floating-point error, `double` can be appropriate. What matters is **never using locale-formatted display strings to mask precision errors or choosing the wrong numeric type for the requirement**.

### equals, compareTo, and scale

These two objects:

```java
BigDecimal x = new BigDecimal("1.0");
BigDecimal y = new BigDecimal("1.00");
```

satisfy `x.compareTo(y) == 0` while `x.equals(y)` is `false` because `equals` compares both value and scale. When exchanging decimal strings, decide whether scale information must be preserved or only numeric comparison is needed.

Do not blindly call `stripTrailingZeros()` on all monetary amounts if trailing fractional digits carry meaning in the product contract. Conversely, if a schema requires a canonical representation without trailing zeros, document that normalization step and test it.

## 6. Standalone Java 17+ Example: One Number, Two Representation Layers

Create `NumberDisplayVsWire.java`:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;

public class NumberDisplayVsWire {

    private static DecimalFormat formatter(Locale locale) {
        DecimalFormat format =
                (DecimalFormat) NumberFormat.getNumberInstance(locale);
        format.setGroupingUsed(true);
        format.setMaximumFractionDigits(3);
        format.setRoundingMode(RoundingMode.HALF_UP);
        return format;
    }

    public static void main(String[] args) {
        BigDecimal value = new BigDecimal("12345.6789");

        DecimalFormat german = formatter(Locale.GERMANY);
        DecimalFormat american = formatter(Locale.US);

        String deDisplay = german.format(value);
        String usDisplay = american.format(value);
        String wire = value.toPlainString();

        System.out.println("de display: " + deDisplay);
        System.out.println("us display: " + usDisplay);
        System.out.println("wire: " + wire);

        german.setParseBigDecimal(true);
        ParsePosition position = new ParsePosition(0);
        Number parsed = german.parse(deDisplay, position);

        System.out.println("parsed: " + parsed);
        System.out.println("all consumed: "
                + (parsed != null
                && position.getIndex() == deDisplay.length()));
        System.out.println("original preserved: "
                + (parsed instanceof BigDecimal
                && value.compareTo((BigDecimal) parsed) == 0));

        ParsePosition suffixPos = new ParsePosition(0);
        Number withSuffix = german.parse(deDisplay + "abc", suffixPos);
        System.out.println("suffix rejected as full input: "
                + (withSuffix == null
                || suffixPos.getIndex() != (deDisplay + "abc").length()));

        try {
            new BigDecimal(deDisplay);
            System.out.println("unexpected decimal accepted");
        } catch (NumberFormatException ex) {
            System.out.println("localized string is not wire decimal");
        }
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 NumberDisplayVsWire.java
java NumberDisplayVsWire
```

Stdout with the stated `Locale` and formatter settings:

```text
de display: 12.345,679
us display: 12,345.679
wire: 12345.6789
parsed: 12345.679
all consumed: true
original preserved: false
suffix rejected as full input: true
localized string is not wire decimal
```

Explanation:

- The first two lines show the same `BigDecimal` using German and US separators. The formatter caps decimal places at 3 with `HALF_UP`, so `12345.6789` becomes `...679`.
- The `wire` line uses `toPlainString()` to preserve all decimal digits held by the `BigDecimal`.
- `setParseBigDecimal(true)` lets `DecimalFormat` return a `BigDecimal` instead of defaulting to `Long`/`Double` depending on content.
- `all consumed: true` only indicates the display string was fully processed by the parser. `original preserved: false` demonstrates that **even full-string parsing cannot undo display rounding**.
- When `abc` is appended, the parser can successfully parse the **prefix** without consuming the entire input; checking the index catches the leftover suffix.
- `new BigDecimal(deDisplay)` rejects German grouping and decimal characters. `BigDecimal(String)` is not a parser for locale-formatted display strings.

The example deliberately separates `deDisplay`, `usDisplay`, and `wire`: they represent three different **roles** of text. Never name a single variable `numberString` and mix it across UI and database/API layers.

## 7. Converting Back from User Input: Parsing Must Follow the Input Contract

An application may **need to accept locale-formatted numbers entered by users**. In that case parsing is appropriate, provided the input has an explicit context.

For example, an input box for a user selecting `Locale.GERMANY` might accept:

```text
12.345,67
```

whereas the same value displayed under `Locale.US` might be:

```text
12,345.67
```

Passing both into `Double.parseDouble(...)` or `new BigDecimal(...)` does not solve multilingual UIs. Those two APIs do not arbitrarily understand every locale's decimal/grouping separators.

With a dedicated parser:

```java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;

static BigDecimal parseUserDecimal(String raw, Locale locale) {
    if (raw == null || raw.isEmpty()) {
        throw new IllegalArgumentException("A number is required");
    }

    DecimalFormat format =
            (DecimalFormat) NumberFormat.getNumberInstance(locale);
    format.setParseBigDecimal(true);

    ParsePosition position = new ParsePosition(0);
    Number parsed = format.parse(raw, position);

    if (!(parsed instanceof BigDecimal)
            || position.getIndex() != raw.length()) {
        throw new IllegalArgumentException("Invalid localized number");
    }

    return (BigDecimal) parsed;
}
```

This is an **illustrative method**, placed inside a Java class. It checks that the entire input was read; this is a necessary step, yet **not sufficient to consider the input strictly valid for every business rule**.

### Display-Oriented Parsers Can Accept Loose Syntax

An easily overlooked point: `NumberFormat`/`DecimalFormat` was not designed to replace strict grammar validators. Depending on locale, pattern, and options, the parser may accept improperly placed grouping separators. Even when `ParsePosition.getIndex() == raw.length()`, **the entered format can still violate application-specific rules**.

For example, with a standard German formatter, an anomalously grouped string like `1.23.45,678` may still be accepted by the parser as a number. Therefore:

1. Decide whether the input allows grouping separators at all.
2. If allowed, clearly define valid group sizes and which whitespace characters are permitted.
3. Use schema validation or a suitable parser to reject unwanted syntax rather than relying solely on the formatter returning a `Number`.
4. Check range, scale, unit, and business validity **after** parsing.
5. Keep the chosen input `Locale` explicit; do not guess the locale from a comma since `"1,234"` is ambiguous.

Never automatically replace every comma with a period before parsing: `"1,234"` could mean one thousand two hundred thirty-four in en-US or one point two three four in other conventions. Unconditional symbol replacement can cause users to pay amounts off by a factor of a thousand.

### Distinguish Human Input from Machine Input

You can design two distinct endpoints/processing pipelines:

- **Form UI:** accepts strings in an identified locale, parses and validates, then constructs `BigDecimal`.
- **REST/CSV import from another system:** accepts a representation matching a fixed schema; parses without locale, or decodes JSON numbers into the agreed data type.

Do not reuse the UI screen's parser at the network layer just because "it already handles commas." Locale settings on the sending system could shift unexpectedly; exchange formats should always follow documented rules tested across systems.

## 8. JSON, CSV, and Databases: Examples of Choosing the Right Representation

### JSON API

If an API requires exact decimal numbers, a common choice is:

```json
{
  "amount": "12345.6789",
  "currency": "EUR"
}
```

In this contract, `amount` **is a decimal string conforming to a specified grammar**, not "arbitrary display text." The receiver can construct `new BigDecimal(amount)` after checking length, characters, scale, bounds, and value. If using a JSON number instead, you must know whether serializers/parsers on both sides preserve the required precision.

If the data is a countable integer quantity, `{"quantity": 12345}` as a JSON number can be cleaner and clearer. Even for integers, consider type limits and client precision, especially for large numbers exceeding JavaScript's safe integer range.

### CSV

CSV is fundamentally a **textual table format** with no built-in decimal type guarantee. A canonical exchange column can use:

```csv
order_id,amount,currency
A-100,12345.6789,EUR
A-101,-10.25,USD
```

Clearly document that `amount` uses ASCII digits, `.` for decimal, and no grouping separators; `currency` uses ISO codes. If exporting CSV specifically to **open in spreadsheets for human readers**, locale-specific display or spreadsheet import rules are a separate problem. Never claim a CSV is "locale-neutral" without a defined schema.

In particular, when a locale uses a comma as the decimal separator, an unquoted string like `12,34` can be split into **two columns** in a comma-delimited CSV. Even when quoted, the importing system still needs to know which locale `12,34` belongs to. For machine-to-machine interoperability, agree on decimal marks and delimiters in the contract.

### SQL / JDBC

In a database, prefer **NUMERIC/DECIMAL** columns for decimals requiring precision rather than storing formatted text:

```java
BigDecimal price = new BigDecimal("12345.6789");
preparedStatement.setBigDecimal(1, price);
```

This is an illustrative snippet inside a method with a valid `PreparedStatement preparedStatement`. Choose column precision/scale per business requirements, handle values that exceed column bounds, and store currency/unit if needed.

JDBC supports passing `BigDecimal` values directly to the driver; never build SQL strings like:

```java
// Not recommended:
String sql = "INSERT INTO sales (amount) VALUES ('"
        + numberFormat.format(price) + "')";
```

The snippet above illustrates an **anti-pattern** (assuming `numberFormat` and `price` exist). Beyond locale formatting and type errors, string concatenation to construct SQL introduces security risks when external input is involved. Always use prepared statements and strongly typed parameters.

### Do Not Treat Every Number as Money

Even when a schema uses `BigDecimal`, units still matter: is `0.25` equal to 25% or 0.25%? Is `100` equal to 100 kg or 100 g? A stable format cannot convey unit semantics by itself if the contract omits them. Name fields clearly, include units or required metadata, and only then format for users.

## 9. Precision, Scale, Rounding, and Special Values

### Control Rounding in Business Logic, Not in the UI

If billing requires rounding to two decimal places, deciding **when and how** to round belongs to business logic, not as a side effect of an on-screen formatter.

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal calculated = new BigDecimal("10.005");
BigDecimal charged = calculated.setScale(2, RoundingMode.HALF_UP);
```

This is an illustrative snippet inside a method; `charged.toPlainString()` is `10.01`. `RoundingMode.HALF_UP` is merely an **illustrative rule**; a product may require a different rule due to regulations, currency, or contracts.

Do not format `calculated` to `10.01` and parse it back in order to "round." Process numbers with arithmetic APIs and business rules, and format only for display.

### double, NaN, and Infinity

`double` can hold `NaN`, `Double.POSITIVE_INFINITY`, or `Double.NEGATIVE_INFINITY`. Those are not valid JSON numbers. When serializing, serializers must obey the schema (typically rejecting them or applying a dedicated rule), rather than assuming JSON accepts `NaN` as a number just because `Double.toString` produces the text `NaN`.

For exact decimal data, `BigDecimal` does not represent these special values. When accepting floating-point values, check `Double.isFinite(value)` if only finite numbers are allowed.

### Negative Zero, Trailing Zeros, and Scientific Notation

- For `double`, `-0.0` and `0.0` have different arithmetic/bit behaviors in certain contexts; formatted strings may strip or preserve the minus sign.
- For `BigDecimal`, `1.0` and `1.00` are numerically equal yet have different scales; `toPlainString()` reflects their respective scales.
- `BigDecimal.toString()` may use scientific notation when needed; `toPlainString()` never uses scientific notation. Neither replaces range/length contracts.
- Never "canonicalize" data by arbitrarily stripping signs, spaces, or zeros before defining semantics and acceptance limits.

The key point is that **business policies and exchange schemas must be defined independently of locale display preferences**.

## 10. Workflow for Designing a Correct Numeric Data Pipeline

A practical mental model:

```text
      User input (with Locale)
                 |
       Parse + validate input
                 |
         BigDecimal / Number
                 |
      Business logic + rounding
          /               \
         v                 v
  Locale Formatter    Schema Serializer
         |                 |
         v                 v
   Display string     Canonical number/decimal
     for humans       for storage/exchange
```

Similarly, data received from an API must be parsed per schema **before** being passed to a display formatter:

```text
API / database -> parse per schema -> numeric value -> NumberFormat(locale) -> UI
```

Never connect the two paths directly with `UI String -> save DB` or `API decimal -> raw display` if the product has localization requirements.

### Implementation Checklist

1. **Separate variables:** `amount` is `BigDecimal`; `displayText` is a UI `String`; `wireAmount` is a `String` matching the exchange schema.
2. **Pass explicit locales** to formatters and parsers handling user data.
3. **Do not extract numbers by stripping commas/periods** from arbitrary strings.
4. **Define an input grammar** for APIs/CSVs; never rely on `Locale.getDefault()`.
5. **Enforce precision/scale/range** on parsed numbers; reject rather than silently rounding if the contract requires it.
6. **Choose an appropriate serialization form**: JSON number, decimal string, or integer smallest unit, and document the unit.
7. **Use prepared statements** to pass typed numeric values to the database.
8. **Format at the final step** right before display; never use formatted output as source data.
9. **Handle NaN/Infinity** when using floating-point and the schema disallows them.
10. **Test across locales and environments** including edge cases (large numbers, negatives, 0, fractions, digit grouping, invalid input, trailing zeros).

## 11. Common Misconceptions

| Misconception | Why it is wrong | Proper approach |
| --- | --- | --- |
| Storing `numberFormat.format(amount)` in the database | String is locale-dependent and may be rounded | Store numeric columns or canonical decimal |
| Using `Double.parseDouble("12,34")` | API does not understand every locale's decimal separator | Parse input with known locale or require canonical input grammar |
| Replacing all `,` with `.` to normalize | `1,234` could be thousands grouping or decimal | Identify locale/schema first |
| Stripping all `.` and `,` before parsing | Can scale the value by factors of a thousand | Use formal parsers and validation |
| Assuming `NumberFormat.parse` reads all input | Parser may accept a valid prefix and ignore the tail | Check `ParsePosition.getIndex()` |
| Assuming full consumption guarantees valid grouping syntax | Some parsers accept lenient grouping | Add business grammar checks |
| Assuming `parse(format(x)) == x` | Formatter may round and alter scale | Keep raw value; format only for display |
| `new BigDecimal(0.1)` to represent decimal `0.1` | Captures exact binary64 value with trailing digits | Construct from validated string or consider `valueOf` |
| Using currency formatter to determine transaction currency | Locale does not dictate business currency | Store currency code separately |
| Calling `NumberFormat.getInstance()` without locale in an API | Output varies by JVM environment | Choose a fixed schema; keep locale in UI only |
| Assuming JSON numbers always preserve all digits | Clients may parse as `double` and lose precision | Define types and limits; use decimal strings when needed |
| Putting `NaN`/`Infinity` into JSON numbers | Invalid per JSON number grammar | Validate finite or define a custom representation |
| Concatenating formatted strings into SQL | Wrong separators/types and SQL injection risk | `PreparedStatement#setBigDecimal` |
| Using `String` for arithmetic | Arithmetic and comparison violate numeric semantics | Parse into numeric types, compute, then serialize |

## 12. Self-Check Exercises

**Exercise 1 — Two display formats:** Given `12345.6789` and a limit of at most 3 decimal places, write two `NumberFormat` calls for `US` and `GERMANY` locales. Why do the two strings differ while the original `BigDecimal` stays unchanged? What data is lost during formatting?

**Exercise 2 — Ambiguous number:** A form submits `"1,234"`. Give at least two interpretations when the locale is unknown and explain why `replace(",", ".")` is unsafe.

**Exercise 3 — Exact numbers:** Why does `new BigDecimal("0.1")` differ from `new BigDecimal(0.1)`? When does `BigDecimal.valueOf(0.1)` produce a shorter string? What does this say about passing decimal numbers through `double`?

**Exercise 4 — Round-trip:** Use `DecimalFormat` to display `new BigDecimal("9.9999")` with two decimal places. If you parse the string back, why can the original number not be reliably recovered?

**Exercise 5 — Money API:** Design a minimal schema for a EUR monetary amount requiring exact decimal precision. Choose either a JSON number or decimal string, include the currency code, and describe scale/range limits and rounding rules in the contract.

**Exercise 6 — Strict parsing:** With `"12.345,678abc"` and `Locale.GERMANY`, why can the parser return a value yet the input is still invalid? Use `ParsePosition` to verify whether the entire string was consumed.

**Exercise 7 — Storage:** Compare a SQL column `VARCHAR("12.345,67")` against `DECIMAL(18,2)` holding the corresponding numeric value. What happens if the application switches its UI language to en-US? Why should locale changes never alter stored numeric data?

## 13. Conclusion

A **display string** is a product of `Locale` and presentation policy: readable for humans, possibly containing grouping separators, currency symbols, or non-ASCII digits, and possibly rounded. A **storage/exchange representation** must use a numeric type or a fixed text grammar, with precision/scale, range, and units defined by schema—independent of language or default locale.

In Java, use `NumberFormat`/`DecimalFormat` at the UI layer; use `BigDecimal` for decimals needing exactness; consider `toPlainString()` when a canonical non-exponent decimal string is required by contract; use strongly typed JDBC parameters and appropriate JSON serializers. When accepting text from users, parse with the known locale and validate strictly; when receiving data from other systems, parse according to the **agreed exchange schema**.

Concise principle: **Keep the numeric value as the source of truth. Format when displaying, serialize when exchanging—never swap the two responsibilities.**

### API References

- [`NumberFormat` – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html)
- [`DecimalFormat` – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormat.html)
- [`BigDecimal` – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html)
- [`ParsePosition` – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/ParsePosition.html)