# Validating Full Input Consumption When Parsing Localized Data in Java

## 1. The Problem: Successful Parsing Does Not Mean the Whole String Is Valid

In applications handling locale-sensitive numbers or dates, a dangerous situation occurs when **the parser reads a valid prefix and leaves behind trailing data that the application never checks**.

For example, with a US number formatter:

```text
Input:          1,234.50kg
Parsed portion: 1,234.50
Remainder:              kg
```

`NumberFormat.parse("1,234.50kg")` can return `1234.5` instead of throwing an error, because parse APIs on `java.text.Format` subclasses typically read from the start of the string until they can no longer recognize valid tokens. That behavior is convenient when parsing embedded values, but **unsuitable when an input field must contain only a single number**.

Key rule:

> **A fully valid input requires two conditions:** the parser produces a result and **the ending parse position equals the length of the acceptable input string**.

For `java.text` parsers supporting `ParsePosition`, use:

```java
ParsePosition position = new ParsePosition(0);
Number number = numberFormat.parse(input, position);
boolean fullyParsed =
        number != null && position.getIndex() == input.length();
```

There is still another layer: **consuming the entire string is only a necessary condition**, not sufficient to guarantee strict grammar, valid value range, precision, or business policy compliance. For example, a parser might accept non-standard digit grouping even after reading every character.

## 2. Three Parsing Outcomes to Distinguish

When calling `NumberFormat.parse(String, ParsePosition)` or a similar API, classify the outcome:

| Status | Return Value | `position.getIndex()` | Meaning |
|---|---|---|---|
| Full success | Non-`null` | `input.length()` | Parser consumed the entire string |
| Partial success | Non-`null` | Less than `input.length()` | Unchecked remainder exists |
| Failure | `null` | Usually does not advance past start | Could not produce a value |

Examples on `NumberFormat` with `Locale.US`:

| Input | Parsed Value | Ending Index | Length | Full-Consumption Conclusion |
|---|---:|---:|---:|---|
| `1,234.50` | `1234.5` | 8 | 8 | Accept |
| `1,234.50kg` | `1234.5` | 8 | 10 | Reject |
| `12.5kg` | `12.5` | 4 | 6 | Reject |
| `12.5 ` | `12.5` | 4 | 5 | Reject if trailing whitespace is disallowed |
| `abc12` | `null` | 0 | 5 | Reject |
| `1,23` | `123` | 4 | 4 | Fully consumed, but grouping syntax may violate policy |

The last row reiterates a limitation of this check: some `NumberFormat` implementations **do not validate grouping positions strictly**. Thus `1,23` can become `123` in `Locale.US` with no trailing characters left. If the product requires exact three-digit grouping, add an explicit rule check.

## 3. Why `parse(String)` Is Not Enough for Validation

`NumberFormat` offers a convenient overload:

```java
Number value = numberFormat.parse(input);
```

This overload throws `ParseException` when the parser **cannot begin parsing a value**, yet it can accept a **valid prefix** and ignore the rest. It does not force you to check the ending position.

Example:

```java
NumberFormat formatter =
        NumberFormat.getNumberInstance(Locale.US);

System.out.println(formatter.parse("12.5kg"));
```

Prints:

```text
12.5
```

Whereas:

```java
formatter.parse("abc12");
```

throws `ParseException` because no number can be parsed at the starting position.

Therefore, wrapping `parse(String)` in `try/catch(ParseException)` is **still not a “whole-string parsed” check**.

The preferred pattern is `parse(input, ParsePosition)` combined with an ending-index check, especially when data comes from web forms, manual entry, CSVs, protocol messages, or untrusted user content.

## 4. `ParsePosition`: What Do `index` and `errorIndex` Mean?

`java.text.ParsePosition` stores parser state via two main indices:

- `getIndex()`: position **after the last successfully parsed character**. When initialized with `new ParsePosition(0)`, this index reflects the number of UTF-16 code units consumed.
- `getErrorIndex()`: position where an error occurred if parsing failed; defaults to `-1`, meaning **no error index was recorded**.

A parse snippet:

```java
String input = "12.5kg";
ParsePosition position = new ParsePosition(0);

Number value = formatter.parse(input, position);
```

Afterward, observed values are:

```text
value      = 12.5
index      = 4
errorIndex = -1
length     = 6
```

**Never check only `errorIndex == -1` to conclude the input is valid.** `12.5kg` parsed partially, recorded no error index, and still left trailing data.

You must evaluate both together:

```java
value != null && position.getIndex() == input.length()
```

When the parser fails right at the start, `getErrorIndex()` helps pinpoint the error if recorded. For unparseable `"abc12"` in the US example, the value is `null`, `getIndex() == 0`, and `getErrorIndex() == 0`.

### Indices Are UTF-16, Not Perceived Character Counts

`ParsePosition` uses Java `String` indices. Under Unicode, `input.length()` counts UTF-16 code units, not UTF-8 bytes or grapheme clusters. The check `position.getIndex() == input.length()` **uses matching index units**; do not replace `length()` with a code-point count when comparing directly.

### Always Create a Fresh `ParsePosition` for Each Check

`ParsePosition` is stateful and can start at a non-zero index. When validating an entire string, create `new ParsePosition(0)` for **each check**. If you intentionally parse from the middle of a string, interpret indices relative to that starting offset; do not treat a mid-string result as “whole-string parsed.”

## 5. Complete Java 17+ Example: Rejecting Any Remainder

Create the file `FullNumberParseDemo.java`:

```java
import java.text.NumberFormat;
import java.text.ParseException;
import java.text.ParsePosition;
import java.util.List;
import java.util.Locale;
import java.util.Objects;

public class FullNumberParseDemo {
    public static Number parseFully(
            NumberFormat formatter,
            String input) throws ParseException {

        Objects.requireNonNull(formatter, "formatter");
        Objects.requireNonNull(input, "input");

        ParsePosition position = new ParsePosition(0);
        Number result = formatter.parse(input, position);

        if (result == null ||
                position.getIndex() != input.length()) {
            int errorOffset = position.getErrorIndex() >= 0
                    ? position.getErrorIndex()
                    : position.getIndex();

            throw new ParseException(
                    "Input was not fully parsed", errorOffset);
        }

        return result;
    }

    public static void main(String[] args) {
        NumberFormat formatter =
                NumberFormat.getNumberInstance(Locale.US);

        for (String input : List.of(
                "1,234.50",
                "1,234.50kg",
                "12.5",
                "12.5 ",
                "abc12",
                "1,23")) {

            try {
                Number value = parseFully(formatter, input);
                System.out.println(
                        "[" + input + "] -> ACCEPT " + value);
            } catch (ParseException exception) {
                System.out.println(
                        "[" + input + "] -> REJECT at " +
                        exception.getErrorOffset());
            }
        }
    }
}
```

Compile and run:

```bash
javac FullNumberParseDemo.java
java FullNumberParseDemo
```

Output:

```text
[1,234.50] -> ACCEPT 1234.5
[1,234.50kg] -> REJECT at 8
[12.5] -> ACCEPT 12.5
[12.5 ] -> REJECT at 4
[abc12] -> REJECT at 0
[1,23] -> ACCEPT 123
```

Exact breakdown of each outcome:

1. `1,234.50` is fully read and returns `1234.5`.
2. `1,234.50kg` reads only the numeric part in the first eight characters; the remaining `kg` causes rejection.
3. `12.5` is fully read.
4. `12.5 ` leaves **one trailing space**; since the function's policy forbids any extra characters, it is rejected.
5. `abc12` has no valid numeric prefix; the parser returns `null` and `getErrorIndex()` is 0.
6. `1,23` is fully accepted by the US parser as `123`; this demonstrates that **full consumption does not imply strict grouping**.

In the example, `ParseException.getErrorOffset()` for partially parsed input is the parse stopping position explicitly passed by our helper to the constructor. That is **information constructed by our validation function**, not an error that `NumberFormat` throws automatically for trailing text.

This function uses `Objects.requireNonNull` to fail fast when invoked with `null` arguments; you can substitute another validation policy if your application contract requires it.

## 6. Distinguishing No Progress from Partial Consumption

A complete check should verify a **non-`null` value** before relying on the index:

```java
ParsePosition pos = new ParsePosition(0);
Number number = formatter.parse(input, pos);

boolean valid = number != null && pos.getIndex() == input.length();
```

Do not write only:

```java
boolean valid = pos.getIndex() == input.length();
```

If the input is empty, `input.length() == 0` and `pos.getIndex()` can remain `0` even though the parser produced no value, breaking validation.

Likewise, if the parser records no `errorIndex` yet returns a partially parsed value, you must still check the ending position. `getErrorIndex()` is **debugging diagnostic data**, not a flag affirming the whole input is valid.

In production applications, user-facing error messages should generally omit raw sensitive input strings. You can return an error type like “Invalid numeric value” and log the error index to an appropriate internal channel.

## 7. Whitespace: Reject or Intentionally Normalize?

Many forms allow users to type `" 12.5 "` and strip surrounding whitespace. A validator **must not make arbitrary assumptions** on the user's behalf; the policy must be explicit.

### Policy A — Exact Input

Use the original string as-is:

```java
Number number = parseFully(formatter, raw);
```

`"12.5 "` is rejected because of trailing characters. Leading whitespace in `" 12.5"` may prevent parsing from starting.

### Policy B — Allow Leading/Trailing Whitespace

Normalize **before parsing**:

```java
String normalized = raw.strip();
Number number = parseFully(formatter, normalized);
```

`String.strip()` follows Java's whitespace rules, which differ from `trim()` in Unicode details; do not assume every kind of Unicode space is removed. After normalizing, you must compare the parse index against **`normalized.length()`**, not `raw.length()`.

If the input contains special whitespace belonging to that locale's number format (for example, a non-breaking space used as a grouping separator), deleting whitespace **inside** the string can corrupt the input. Normalize only what the policy explicitly permits; never strip all spaces with `replace(" ", "")` and call it strict parsing.

### Policy C — Accept Units Only If Handled Explicitly

If valid input is `"12.5kg"`, you cannot call `parseFully` on the entire string just to extract the number and still accept it. Instead, use an **intentional grammar**: separate/parse both the numeric part and the unit, verify the unit is in the allowlist, and ensure no leftover data remains.

For example, accepting only `kg` and `g` is completely different from ignoring whatever follows a number. Blindly discarding trailing text loses unit semantics and causes business bugs.

## 8. Consuming the Whole String Does Not Mean the Parser Verified Exact Shape

An important question: why does `NumberFormat.getNumberInstance(Locale.US)` parse `"1,23"` into `123` while consuming all four characters?

Because `NumberFormat` / `DecimalFormat` can have **relatively permissive parsing rules** for grouping. That helps accept varied UI inputs, but it does not enforce every syntactic constraint you might want, such as requiring commas between exact three-digit groups.

Depending on the application contract, add explicit validation:

- Are grouping separators allowed? If so, what exact positions must they occupy?
- Is a negative sign allowed? Is a plus sign accepted?
- Are non-ASCII digits allowed?
- How many fractional digits are permitted at most?
- Are currency or percent signs allowed?
- Are leading `0`s, negative zero, `NaN`, or infinity accepted?
- After parsing, is the value within the business domain range?

**Example of an intentional machine/ASCII decimal syntax without grouping**:

```java
boolean validText =
        input.matches("[0-9]+(?:\\.[0-9]{1,2})?");
```

This accepts one or more ASCII digits, optionally followed by a dot and one or two fractional digits. `String.matches(...)` matches the **entire** string against the regex. It forbids minus signs, grouping separators, and digits from other numeral systems; those are **intentional constraints**, not a grammar for every locale.

After verifying that grammar, if the input is truly a canonical decimal string (without grouping), you can convert directly:

```java
java.math.BigDecimal amount = new java.math.BigDecimal(input);
```

For **localized input** according to a `Locale`, do not treat an ASCII regex as a global standard. Combine a locale-aware parser, full-consumption checking, and grammar/value validation per specific policy. Never claim “using `ParsePosition` guarantees the input matches standard formatting.”

## 9. Locale Affects Both Decimal Separators and Parse Outcomes

The same string can mean different things depending on language/region:

- `Locale.US` typically formats `1234.5` as `1,234.5`.
- `Locale.GERMANY` typically formats the corresponding value as `1.234,5`.

Side-by-side comparison:

| Parser Locale | Input | Parsed Value | Ending Index | Conclusion |
|---|---|---:|---:|---|
| `en-US` | `1,234.50` | `1234.5` | 8/8 | Fully parsed |
| `en-US` | `1.234,50` | `1.234` | 5/8 | Remainder left |
| `de-DE` | `1.234,50` | `1234.5` | 8/8 | Fully parsed |
| `de-DE` | `1,234.50` | `1.234` | 5/8 | Remainder left |

These results were observed with the locale/JDK dataset used for the example; exact symbols can depend on locale configuration, especially for other locales or newer Unicode data.

Therefore, an application must never format with one locale and parse with another. If the UI indicates the user is entering data in `vi-VN`, construct the parser according to that locale/input contract. If a machine-to-machine API defines a fixed decimal dot, use the protocol's canonical grammar rather than guessing from the server OS locale.

A great debugging question: “Is this input valid?” must always be paired with “**Valid under which locale and grammar?**”

## 10. `BigDecimal`: Preserving Decimal Representation Does Not Replace Full Consumption

`NumberFormat.parse(...)` returns a `Number`, which may be `Long`, `Double`, or another type depending on the formatter and input. For monetary amounts or decimals needing exactness, configure a `DecimalFormat` explicitly:

```java
DecimalFormat formatter = new DecimalFormat(
        "#,##0.###",
        DecimalFormatSymbols.getInstance(Locale.US));
formatter.setParseBigDecimal(true);
```

Then, for ordinary finite decimal numbers, the parser can return `BigDecimal`. For example, `1,234.50` is parsed into a `BigDecimal` representing `1234.50`, preserving the fractional part as read by the parser.

**However, `setParseBigDecimal(true)` does not force the parser to consume the entire input.** `"1,234.50kg"` can still return `BigDecimal("1234.50")` with index 8/10. Nor does it make grouping validation strict.

Additionally, special values such as `NaN` or infinity may still be returned as `Double` even when `setParseBigDecimal(true)` is enabled. If business logic requires strictly finite `BigDecimal` values, check the output type and domain explicitly.

A clean workflow breaks the process into steps:

1. Select the right `Locale` and `DecimalFormatSymbols`.
2. Define supported grammar, precision/scale, and grouping rules.
3. Parse with `ParsePosition` starting at index 0.
4. Reject if parsing yields no value or fails to consume the full string.
5. Validate type, sign, precision, scale, and min/max per business rules.
6. Only then pass the value into calculations.

Keep **data type**, **text syntax**, and **valid value domain** distinct: checking one does not replace the other two.

## 11. Dates: `setLenient(false)` Can Still Leave Trailing Data

The issue is not limited to numbers. Legacy `java.text.DateFormat` / `SimpleDateFormat` APIs also support `ParsePosition`.

For example, with pattern `dd/MM/yyyy`:

- `28/02/2026` is a valid date under the pattern.
- `28/02/2026abc` has a **valid date prefix**, leaving `abc` behind.
- `31/02/2026` is not a valid calendar date.

`setLenient(false)` rejects nonexistent dates, but **does not guarantee the parser consumed the entire string**.

### Complete Java 17+ Example

Save as `FullDateParseDemo.java`:

```java
import java.text.ParsePosition;
import java.text.SimpleDateFormat;
import java.util.Locale;

public class FullDateParseDemo {
    public static void main(String[] args) {
        SimpleDateFormat formatter =
                new SimpleDateFormat("dd/MM/yyyy", Locale.ROOT);
        formatter.setLenient(false);

        for (String raw : new String[] {
                "28/02/2026",
                "28/02/2026abc",
                "31/02/2026"
        }) {
            ParsePosition pos = new ParsePosition(0);
            Object date = formatter.parse(raw, pos);

            boolean valid = date != null &&
                    pos.getIndex() == raw.length();

            System.out.printf(
                    "%s -> valid=%s index=%d error=%d%n",
                    raw, valid, pos.getIndex(), pos.getErrorIndex());
        }
    }
}
```

Compile and run:

```bash
javac FullDateParseDemo.java
java FullDateParseDemo
```

Output:

```text
28/02/2026 -> valid=true index=10 error=-1
28/02/2026abc -> valid=false index=10 error=-1
31/02/2026 -> valid=false index=0 error=10
```

We need **both checks**:

- `setLenient(false)` checks calendar date validity.
- `pos.getIndex() == raw.length()` checks that no trailing text remains.

Although this example uses `SimpleDateFormat` to demonstrate `ParsePosition`, new applications should consider `java.time.LocalDate` and `DateTimeFormatter`. `LocalDate.parse(text, formatter)` normally parses the entire string and can be paired with `ResolverStyle.STRICT` for strict date rules. When choosing year pattern letters under strict resolution, understand the difference between `yyyy` (year-of-era) and `uuuu` (proleptic year), making `dd/MM/uuuu` a clear choice. Do not mix parse results from `SimpleDateFormat` and `DateTimeFormatter` while ignoring differences in resolvers/styles.

## 12. A Reusable Helper Method: Clear Error Contract

`parseFully` can return `Number` or throw `ParseException`. In backend systems, you can map errors to business-meaningful categories such as `INVALID_NUMBER` or `TRAILING_CHARACTERS`.

When keeping `ParsePosition`, you can separate failure modes:

```java
ParsePosition pos = new ParsePosition(0);
Number value = formatter.parse(input, pos);

if (value == null) {
    // Could not parse a prefix at the start position.
} else if (pos.getIndex() < input.length()) {
    // Valid number at start, but trailing characters remain.
} else {
    // Parse consumed the entire string; proceed to business validation.
}
```

This is a **code snippet** assuming `formatter` and `input` are already declared. `ParsePosition` supplies the index to inspect the remainder:

```java
String remainder = input.substring(pos.getIndex());
```

In the `12.5kg` example, `remainder` is `kg`. Use this only for helpful user feedback or debugging when appropriate; never automatically drop the remainder and feed the number into the system without an explicit policy.

If a parser tokenizes multiple consecutive fields in a single string, it can advance `ParsePosition` and continue parsing; in that case, a single partial parse is not an error **as long as the application eventually verifies that the entire input was consumed according to the grammar**. For an input field expecting **a single number**, the full-consumption check must happen right after that parse.

## 13. Security and Data Integrity Pitfalls

Accepting a valid prefix can cause several classes of bugs:

- **Silently dropping measurement units:** `12kg` is interpreted as `12` in a unitless field.
- **Silently dropping currency symbols/text:** strings with unexpected symbols get truncated, causing misinterpretation.
- **Trailing payload after a number:** `100;DROP...` gets accepted as `100` if the application only checks that parsing succeeded; even though the parser does not execute the payload, it can mask malformed data entering downstream steps.
- **Arithmetic errors from locale mismatch:** `,` and `.` have different meanings across locales; partial parsing can silently yield wrong values.
- **Precision loss:** numbers exceeding domain limits or coerced into `double` despite needing exact decimal arithmetic.
- **Inconsistent parsing:** one layer uses `Locale.US`, while another uses the JVM default locale.

A solid validation policy defines the **input domain** and **acceptable source strings**, rather than relying solely on whether the parser “returned a value.”

Beyond full consumption, consider input length limits to avoid unnecessary load and validate domain constraints (negative numbers, precision, scale, range). Avoid dumping raw sensitive inputs into error logs; log the error index, error category, and an appropriate request ID instead.

## 14. Common Mistakes to Avoid

1. **Catching only `ParseException` from `parse(String)` and concluding the whole input is valid.** That overload can accept a valid prefix.
2. **Checking only `result != null`.** A non-`null` result can still leave a suffix behind.
3. **Checking only `errorIndex == -1`.** Parsers usually do not treat trailing text as an internal parse error.
4. **Comparing `index == length` while forgetting `result != null`.** Empty input can leave both `index` and `length` at 0.
5. **Truncating the remainder to “fix” input.** Only discard trailing text if the grammar explicitly defines and handles it.
6. **Trimming/stripping after parsing and comparing against the wrong length.** If normalizing, do it beforehand and compare against the normalized string's length.
7. **Treating full consumption as strict grouping.** `1,23` may still be accepted as `123` in US locale.
8. **Believing `setParseBigDecimal(true)` forces full-string parsing.** It changes the value type, not the consumption policy.
9. **Treating `SimpleDateFormat.setLenient(false)` as a substitute for trailing-text checks.** It only governs date interpretation.
10. **Relying on an accidental JVM default locale.** Parsers must follow the actual input locale/contract.
11. **Comparing `ParsePosition` index to byte length or code-point count.** Java string indices use UTF-16 code units.
12. **Reusing `ParsePosition` and forgetting its state.** Create a fresh instance at index 0 for each independent value.
13. **Ignoring unexpected symbols/units because “a number was read.”** Business data must be validated completely.
14. **Skipping numeric type/precision/range checks.** Full consumption is only a parser-level syntactic condition.

## 15. Essential Test Cases

For a numeric input field under `Locale.US`:

| Input | Expected Behavior Under “Single Number, No Remainder” Policy |
|---|---|
| `123` | Accept |
| `123.45` | Accept |
| `1,234.50` | Accept if grouping is allowed |
| `1,234.50abc` | Reject due to suffix |
| `123.45 ` | Reject if trailing whitespace is disallowed |
| ` 123.45` | Reject if leading whitespace is disallowed |
| `abc123` | Reject because unparseable from start |
| Empty string | Reject |
| `1,23` | Reject **if** grammar requires standard three-digit groups; do not rely solely on `ParsePosition` |
| `1.234,50` | Reject or handle explicitly under another locale; never guess |
| Huge number | Reject per business domain if out of bounds |
| Too many decimals | Reject/round per policy without silent precision loss |

For dates, test valid dates, nonexistent dates, and valid dates followed by a suffix. For multi-locale systems, add test cases for decimal/grouping separators, international digits, currency symbols, and special whitespace characters.

## 16. Self-Check Quiz

**Question 1.** Can `NumberFormat.parse("12.5kg")` succeed?

**Answer:** Yes; it can return `12.5` by parsing the prefix. You must use `ParsePosition` to detect the remaining `kg`.

**Question 2.** Does `getErrorIndex() == -1` prove the entire input was consumed?

**Answer:** No. For `12.5kg`, the error index can be `-1` even though `getIndex()==4` is less than `length()==6`.

**Question 3.** What is the core condition when a parser returns `Number`?

**Answer:** `number != null && position.getIndex() == input.length()`, with `ParsePosition` initialized at 0 and a policy forbidding trailing characters.

**Question 4.** `1,23` is parsed by the US parser as `123` with index equal to length. Is that enough to confirm standard US grouping?

**Answer:** No. Separate grammar validation is needed if commas must separate exact three-digit groups.

**Question 5.** Can you call `strip()` before parsing?

**Answer:** Yes, **if the policy allows leading/trailing whitespace**. In that case, compare the index against the length of the **stripped string**, not the original string.

**Question 6.** Does `SimpleDateFormat.setLenient(false)` reject `28/02/2026abc` just because of the suffix?

**Answer:** Not necessarily. It can read the valid date and leave `abc`; you still must compare `ParsePosition.getIndex()` with the input length.

**Question 7.** If an application accepts input like `12.5kg` as a quantity with a unit, what should it do?

**Answer:** Define a grammar containing both numeric and unit parts, parse/validate both components, and reject out-of-grammar characters; never treat units as an ignored remainder.

## 17. Key Takeaways

**Partial parse success is not validation success.** With `java.text` parsers using `ParsePosition`, check that the result is non-`null` **and** `getIndex()` equals `input.length()` (after any allowed normalization). Once you confirm no trailing data remains, continue validating the right `Locale`, grouping rules, value range, and precision. Following the principle “parse the **entire** input against a defined grammar” prevents silent bugs in localized number/date handling and user input processing.

**Official references:** [Java SE 17 — ParsePosition](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/ParsePosition.html) · [Java SE 17 — NumberFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html) · [Java SE 17 — DecimalFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormat.html) · [Java SE 17 — SimpleDateFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/SimpleDateFormat.html).
