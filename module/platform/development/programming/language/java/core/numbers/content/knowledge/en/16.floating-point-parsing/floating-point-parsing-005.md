# Distinguishing Java-Syntax Number Parsing from Locale-Aware Parsing

In Java, **"a string representing a number" does not have just one single syntax**. Technical strings such as `"1234.56"` and `"1.25e3"` are interpreted differently from localized numeric text entered by users, such as `"1,234.56"` in the United States or `"1.234,56"` in Germany.

Two common API families serve **two different input contracts**:

- **Locale-independent syntax, used for machine data:** `Double.parseDouble`, `Float.parseFloat`, `new BigDecimal(String)`. The standard decimal separator is a **dot `.`**, not automatically a user's regional separator convention.
- **Language/region-aware syntax (locale):** `NumberFormat` and `DecimalFormat`. The decimal separator, grouping separator, digit characters, and even negative sign notation can depend on the `Locale` and format configuration.

Example:

```java
double machine = Double.parseDouble("1234.56"); // 1234.56

NumberFormat us = NumberFormat.getNumberInstance(Locale.US);
NumberFormat de = NumberFormat.getNumberInstance(Locale.GERMANY);

double fromUs = us.parse("1,234.56").doubleValue();  // 1234.56
double fromDe = de.parse("1.234,56").doubleValue();  // 1234.56
```

*The lines above are illustrative code placed inside a method, with `import java.text.NumberFormat;`, `import java.util.Locale;`, and a `throws ParseException` declaration or exception handling.*

**Do not use `Double.parseDouble` to directly read user-entered localized strings**, nor use `NumberFormat` in place of a fixed-protocol data parser when strict, completely consistent syntax must be guaranteed.

This lesson belongs to the **Floating-Point Parsing** section in the **Java core – numbers** module. We will go from mechanisms, edge cases, and parse errors to designing safe parsers for Java 17+.

## 1. What is a Locale and how does it relate to numbers?

`java.util.Locale` describes language/region conventions used by internationalized APIs. For a number, `Locale` can affect:

- **Decimal separator:** dot `.` or comma `,`.
- **Digit grouping separator:** comma, dot, regular space, non-breaking space, or a custom grouping character.
- **Digit grouping:** grouping by 3 digits or other grouping conventions.
- **Digits:** some locales use non-ASCII digits and symbols.
- **Negative, percentage, or currency representations:** can vary depending on the `NumberFormat` type.

Two basic examples:

| Mathematical value | String in `Locale.US` | String in `Locale.GERMANY` |
| ---: | --- | --- |
| One thousand two hundred thirty-four point five six | `1,234.56` | `1.234,56` |
| One point five | `1.5` | `1,5` |
| One thousand | `1,000` | `1.000` |

**The danger:** `"1.234"` in US-style data can be interpreted as one point two three four, whereas under German number conventions it can mean one thousand two hundred thirty-four. **You cannot infer numeric meaning from a string alone without a locale/format contract.**

### Default locale vs. explicit locale

```java
Locale current = Locale.getDefault();
NumberFormat format = NumberFormat.getNumberInstance(current);
```

The default locale can change based on the OS, JVM configuration, or modification by another part of the program. If an API must process **fixed-format data**, pass an explicit locale instead of relying on the environment default:

```java
NumberFormat parser = NumberFormat.getNumberInstance(Locale.US);
```

**Choosing `Locale.US` does not turn the parser into a "Java syntax parser"**: it is still a locale-based parser, with grouping rules and parsing behavior that can be lenient. For machine protocols specifying `1234.56`, you should normally use `Double.parseDouble` or `BigDecimal(String)` with explicit validation.

## 2. Double.parseDouble and Float.parseFloat: locale-independent syntax

`Double.parseDouble(String)` returns `double`; `Float.parseFloat(String)` returns `float`. Both process text according to Java's defined floating-point syntax, **without checking `Locale.getDefault()` to automatically switch decimal separators**.

```java
double a = Double.parseDouble("1234.56"); // 1234.56
double b = Double.parseDouble("1.25e3");  // 1250.0
float c = Float.parseFloat("-2.5");      // -2.5f
```

Commonly supported forms:

| Input | Result/meaning |
| --- | --- |
| `"12.5"` | Decimal number 12.5 |
| `"-0.5"` | Negative number -0.5 |
| `"+3.0"` | Positive number with + sign |
| `"1e3"` | 1000.0 |
| `"1.5E-2"` | 0.015 |
| `"0x1.8p1"` | Base-16 floating-point with binary exponent, equal to 3.0 |
| `"NaN"` | Special value NaN |
| `"Infinity"` | Positive infinity |
| `"-Infinity"` | Negative infinity |
| `"1.5f"` or `"1.5d"` | Syntax with type suffix accepted by Java's floating-point parser |

**Do not completely equate source-code literal syntax with runtime strings:** `Double.parseDouble` accepts several literal-like notations such as hexadecimal floats or `f`/`d` suffixes, yet **does not accept underscore digit separators** like Java source code.

```java
double sourceLiteral = 1_234.56; // Java literal with underscores.
// Double.parseDouble("1_234.56"); // NumberFormatException.
```

### Locale-independent decimal point

```java
double correct = Double.parseDouble("1.5"); // 1.5.
// Double.parseDouble("1,5"); // NumberFormatException.
```

`Locale.GERMANY` does not make `Double.parseDouble("1,5")` automatically become 1.5. To parse user data in German format, use `NumberFormat` with the appropriate locale or a syntax clearly defined by the application.

### Whitespace and suffixes: details to remember

`Double.parseDouble` and `Float.parseFloat` allow certain leading/trailing ASCII whitespace according to the parser's trim rules, yet that does not mean grouping separators or arbitrary spaces inside a number are accepted:

```java
double trimmed = Double.parseDouble(" 2.5 "); // 2.5.
// Double.parseDouble("2 5"); // NumberFormatException.
```

Do not assume every kind of Unicode whitespace is automatically stripped. If you need to handle user-entered input, define an explicit `strip`/`trim`, Unicode, and validation policy.

**Do not assume overly large numbers always throw NumberFormatException:** the syntax may be valid while the value exceeds the finite range of `double`.

```java
double overflow = Double.parseDouble("1e309");
System.out.println(Double.isInfinite(overflow)); // true

double underflow = Double.parseDouble("1e-400");
System.out.println(underflow == 0.0); // true
```

Conversely, syntactically invalid strings such as `"1_000.0"` or `"abc"` cause `NumberFormatException`. **Syntactic validity** and **business-domain validity** are two separate questions.

## 3. BigDecimal(String): exact decimal syntax, not locale-aware

`new BigDecimal(String)` reads decimal number text according to the syntax supported by `BigDecimal`. It allows **preserving the exact decimal value** of the input string rather than forcing the value into binary `double`.

```java
BigDecimal amount = new BigDecimal("1234.56");
System.out.println(amount.toPlainString()); // 1234.56
```

`BigDecimal` is suitable when calculating monetary amounts, taxes, or decimal values where rounding rules and `scale` must be controlled.

```java
BigDecimal price = new BigDecimal("0.10");
BigDecimal tax = new BigDecimal("0.20");
BigDecimal sum = price.add(tax);
System.out.println(sum.toPlainString()); // 0.30
```

Avoid writing:

```java
BigDecimal wrong = new BigDecimal(0.1);
```

That takes **the exact binary `double` value approximating 0.1**, rather than reconstructing the intended decimal 0.1. If the input is original decimal text, use `new BigDecimal(text)`. If receiving a valid `double` and intentionally converting it via its normalized decimal representation, consider `BigDecimal.valueOf(double)`, though it does not recover input data that has already lost information.

### BigDecimal(String) also does not understand locale separators automatically

```java
new BigDecimal("1234.56"); // Valid.

// new BigDecimal("1.234,56"); // NumberFormatException.
// new BigDecimal("1,234.56"); // NumberFormatException.
```

To process values **according to a locale while still keeping exact decimals**, you can configure `DecimalFormat.setParseBigDecimal(true)` after determining the right `Locale` and accepted syntax. That is the topic of the next section.

### Difference regarding NaN and Infinity

`BigDecimal` has no NaN or infinity as representable values:

```java
// new BigDecimal("NaN");       // NumberFormatException.
// new BigDecimal("Infinity");  // NumberFormatException.
```

If the system requires finite numbers, that can be a beneficial property. If the source is a `double`, check `Double.isFinite` before converting to an exact decimal type.

## 4. NumberFormat: parsing by Locale

`java.text.NumberFormat` is the abstract class for formatting and parsing numbers according to a locale. Commonly used factory methods:

- `NumberFormat.getNumberInstance(locale)`: formats/parses general numbers.
- `NumberFormat.getIntegerInstance(locale)`: configured for integers; understand the implementation's rounding/parsing rules.
- `NumberFormat.getPercentInstance(locale)`: formats/parses percentages according to locale conventions.
- `NumberFormat.getCurrencyInstance(locale)`: formats/parses monetary amounts with currency signs.

Example parsing general numbers for US and Germany:

```java
NumberFormat us = NumberFormat.getNumberInstance(Locale.US);
NumberFormat german = NumberFormat.getNumberInstance(Locale.GERMANY);

Number x = us.parse("1,234.56");      // 1234.56
Number y = german.parse("1.234,56");  // 1234.56
```

`NumberFormat.parse(String)` throws **`ParseException`** if it cannot begin parsing a valid value, but there is one crucial point: the method **does not by default require consuming the entire string**.

### Same string, different locale: easily interpreted as a different value

Suppose a user enters `"1,5"`:

- With a German format, the comma is the decimal separator; the intended meaning is usually 1.5.
- With a default US format, the comma is the grouping separator. The parser may interpret grouping separators leniently rather than throwing the error you expect.

Results depend on the locale and the `NumberFormat`/`DecimalFormat` configuration; therefore **do not guess "the user probably meant a decimal comma" and silently swap characters**.

### NumberFormat does not necessarily return Double

`NumberFormat.parse(...)` returns `Number`, not always `Double`:

```java
Number n = NumberFormat.getNumberInstance(Locale.US).parse("42");
```

The actual object type can be `Long`, `Double`, or another `Number` subtype depending on format, value, and configuration. **Do not cast directly to `Double`** without a contract:

```java
// Double d = (Double) n; // May cause ClassCastException.
double value = n.doubleValue(); // May lose precision if n is a large number.
```

If you need exact decimals, configure `DecimalFormat` to return `BigDecimal` as shown later, rather than parsing a `Number` and calling `doubleValue()` before converting to `BigDecimal`.

## 5. ParseException and missed errors: a parser can match only a prefix

A locale-based parser can **successfully parse the beginning of a string and stop**:

```java
NumberFormat us = NumberFormat.getNumberInstance(Locale.US);
Number parsed = us.parse("123xyz");
// Typically parsed is the number 123; the "xyz" part is unused.
```

This is a dangerous situation when an application assumes the entire string was valid. `parse(String)` succeeding **does not by itself prove** the entire input was consumed.

### Using ParsePosition to verify the whole string was parsed

`ParsePosition` tracks the starting index, where the parser stopped (`getIndex()`), and any error index (`getErrorIndex()`). A validation helper can be written as:

```java
static Number parseWhole(String text, NumberFormat format) {
    if (text == null) {
        throw new IllegalArgumentException("Value is required");
    }

    ParsePosition position = new ParsePosition(0);
    Number result = format.parse(text, position);

    if (result == null ||
            position.getIndex() != text.length() ||
            position.getErrorIndex() >= 0) {
        throw new IllegalArgumentException("Invalid localized number");
    }
    return result;
}
```

This is **illustrative code placed inside a class**, requiring imports for `NumberFormat` and `ParsePosition`. For `"123xyz"`, if the parser consumes `"123"` and stops at index 3, the position check will **reject** it because the string has length 6.

**Limitation of this check:** even when the entire string is consumed, `NumberFormat` can still be lenient with grouping, spaces, and other conventions. Consuming the whole string **does not equal strict syntactic validation for all business rules**. If strictly exact syntax is needed, validate the pattern/grouping/length beforehand or pick a specialized parser.

### Why not catch only ParseException?

`NumberFormat.parse(String)` can return a result without throwing `ParseException` when trailing characters remain. Conversely, `parse(String, ParsePosition)` **does not throw ParseException**, instead reporting status via `null`, `index`, and `errorIndex`. The two APIs have different error-reporting rules; handle them according to the overload actually called.

## 6. DecimalFormat.setParseBigDecimal(true): combining locale with exact decimals

`DecimalFormat` is the common `NumberFormat` implementation for decimal numbers. When you need to read **localized decimal numbers** while avoiding an intermediate `double`, you can enable:

```java
DecimalFormat parser =
        (DecimalFormat) NumberFormat.getNumberInstance(Locale.GERMANY);
parser.setParseBigDecimal(true);

BigDecimal amount =
        (BigDecimal) parser.parse("1.234,56");
System.out.println(amount.toPlainString()); // 1234.56
```

This snippet requires handling or declaring `ParseException` if using the `parse(String)` overload; it also relies on the default factory returning a `DecimalFormat` as typical JDK providers do. If a system uses a custom `NumberFormatProvider`, verify the implementation before casting.

**When `setParseBigDecimal(true)` is set:** ordinary finite results are parsed into `BigDecimal`, but special values like NaN/infinity cannot live inside `BigDecimal` and require a separate validation policy rather than blindly casting every input.

For monetary data, you should also check:

- The exact locale of the person entering the data.
- Are thousands grouping separators allowed? Where may grouping separators appear?
- Are plus/minus signs or currency symbols accepted?
- What is the maximum `scale` (number of decimal places)?
- If rounding is needed, which `RoundingMode` is used?
- Must parsing consume the entire string, and is a strict pattern required?

### BigDecimal from a locale parser is not BigDecimal from Double

Avoid:

```java
Number n = NumberFormat.getNumberInstance(Locale.GERMANY)
        .parse("1.234,56");

BigDecimal potentiallyApproximate = new BigDecimal(n.doubleValue());
```

Here the data passed through `double` before entering `BigDecimal`. If you need to preserve exact decimal values from text, enable `setParseBigDecimal(true)` and parse directly into `BigDecimal`.

## 7. NumberFormat and DecimalFormat are stateful: avoid sharing arbitrarily across threads

Formatters in the `NumberFormat`/`DecimalFormat` family are mutable/configurable:

```java
NumberFormat format = NumberFormat.getNumberInstance(Locale.US);
format.setGroupingUsed(true);
format.setMaximumFractionDigits(2);
```

These settings mutate **the behavior of that specific object**. `DecimalFormat` is **not thread-safe**; do not share an unsynchronized mutable instance across multiple requests/workers. In web services, it is common to create a separate instance per request, use a factory, or use a verified safe management strategy.

Also do not arbitrarily call `Locale.setDefault(...)` to parse a single request: doing so can affect other components in the same JVM. Passing an explicit `Locale` makes code much easier to test.

### Formatting for display is not the same as parsing machine data

```java
NumberFormat us = NumberFormat.getNumberInstance(Locale.US);
NumberFormat de = NumberFormat.getNumberInstance(Locale.GERMANY);

String usText = us.format(1234.56); // Typically "1,234.56".
String deText = de.format(1234.56); // Typically "1.234,56".
```

`format` is for localized UI display; output may be capped in decimal places by default configuration. Do not use human-readable display output as a precise data-exchange format without clearly defining the pattern, precision, and rounding policy.

## 8. Strings that "look alike" yet are parsed differently

| String | `Double.parseDouble` | `NumberFormat` US | `NumberFormat` Germany | Takeaway |
| --- | --- | --- | --- | --- |
| `"1234.56"` | 1234.56 | 1234.56 | Dot may be treated as grouping separator | Must pick format explicitly |
| `"1,234.56"` | Syntax error | Typically 1234.56 | Should not be treated as German decimal | Grouping depends on locale |
| `"1.234,56"` | Syntax error | Should not be treated as US decimal | Typically 1234.56 | Dot and comma swap roles |
| `"1,5"` | Syntax error | May treat as grouped digits | 1.5 | Same text can change meaning |
| `"1e3"` | 1000.0 | Depends on locale parser/pattern | Depends on locale parser/pattern | Do not assume exponent support |
| `"NaN"` | NaN | Not a normal finite number | Not a normal finite number | Requires dedicated policy |
| `"0x1.8p1"` | 3.0 | Not standard locale number syntax | Same | Java hex float form |
| `"1_000"` | Error | Not treated as a Java literal automatically | Same | Source underscores differ from data |
| `" 2.5 "` | 2.5 | Per locale parsing rules | Per locale parsing rules | Whitespace needs a contract |

The table illustrates **intent and typical risks**; `NumberFormat` also depends on configuration and providers. Do not extrapolate rigid results for unguaranteed cases, especially when a parser is lenient and accepts a prefix.

## 9. Designing parsers for three practical data streams

### 9.1. Machine protocol data: fixed syntax

Suppose an API defines JSON/text measurements with a decimal dot, no grouping, and no NaN/infinity:

```java
static double parseFiniteMachineDouble(String text) {
    if (text == null) {
        throw new IllegalArgumentException("Value is required");
    }

    final double value;
    try {
        value = Double.parseDouble(text);
    } catch (NumberFormatException ex) {
        throw new IllegalArgumentException("Invalid numeric syntax", ex);
    }
    if (!Double.isFinite(value)) {
        throw new IllegalArgumentException("Finite value required");
    }
    return value;
}
```

The function above uses Java's `parseDouble` syntax, allowing exponents, hexadecimal floats, suffixes, and some whitespace per the parser contract. **If the machine protocol requires a narrower grammar** (e.g., only `-?[0-9]+(\.[0-9]+)?`), validate the grammar **before** or alongside parsing. `Double.isFinite` does not replace character-level validation.

### 9.2. User input form by locale

An application reading measurements from a user can supply the selected locale:

```java
Locale userLocale = Locale.GERMANY;
NumberFormat format = NumberFormat.getNumberInstance(userLocale);
Number number = parseWhole("1.234,56", format);
double value = number.doubleValue();
```

After parsing, validate the data range and `Double.isFinite`. If the value is money or requires exact input decimal digits, use `DecimalFormat.setParseBigDecimal(true)` and an appropriate `BigDecimal`.

For locales whose grouping separator is a **non-breaking space** or special grouping character, do not simply replace all spaces, commas, and dots without understanding Unicode rules. Use a proper locale parser and validate against formats permitted by the system.

### 9.3. Currency / exact decimals

Money does not only require parsing into a value; it also requires:

- **Unit and currency code** (VND, USD, EUR...).
- **Allowed number of decimal digits**.
- **UI format vs. API format**, which may differ.
- An explicit **rounding policy** for division, percentages, and exchange rates.
- **No pass-through via double** if decimal exactness is required.

A solid design typically separates: **localized input text → parser/validation → business-normalized BigDecimal → domain data**; when displaying, run the reverse direction **BigDecimal → localized output text**.

## 10. Standalone runnable Java 17+ program

Save the following as **`LocaleNumberParsingDemo.java`**:

```java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;

public class LocaleNumberParsingDemo {
    static Number parseWhole(String text, NumberFormat format) {
        if (text == null) {
            throw new IllegalArgumentException("Text is required");
        }
        ParsePosition position = new ParsePosition(0);
        Number number = format.parse(text, position);
        if (number == null
                || position.getErrorIndex() >= 0
                || position.getIndex() != text.length()) {
            throw new IllegalArgumentException("Invalid localized number");
        }
        return number;
    }

    static String tryMachineDouble(String text) {
        try {
            return Double.toString(Double.parseDouble(text));
        } catch (NumberFormatException ex) {
            return "INVALID";
        }
    }

    public static void main(String[] args) {
        System.out.println("machine=" +
                Double.parseDouble("1234.56"));
        System.out.println("scientific=" +
                Double.parseDouble("1e3"));
        System.out.println("hex-float=" +
                Double.parseDouble("0x1.8p1"));
        System.out.println("whitespace=" +
                Double.parseDouble(" 2.5 "));
        System.out.println("comma-machine=" +
                tryMachineDouble("1,234.56"));
        System.out.println("underscore-machine=" +
                tryMachineDouble("1_000"));
        System.out.println("overflow-infinite=" +
                Double.isInfinite(Double.parseDouble("1e309")));
        System.out.println("nan=" +
                Double.isNaN(Double.parseDouble("NaN")));

        NumberFormat us = NumberFormat.getNumberInstance(Locale.US);
        NumberFormat de = NumberFormat.getNumberInstance(Locale.GERMANY);

        Number usValue = parseWhole("1,234.56", us);
        Number deValue = parseWhole("1.234,56", de);
        System.out.println("locale-us=" + usValue.doubleValue());
        System.out.println("locale-de=" + deValue.doubleValue());
        System.out.println("locale-same=" +
                (usValue.doubleValue() == deValue.doubleValue()));

        String withSuffix = "123xyz";
        ParsePosition position = new ParsePosition(0);
        Number prefix = us.parse(withSuffix, position);
        System.out.println("prefix=" + prefix +
                ",consumed=" + position.getIndex());
        try {
            parseWhole(withSuffix, us);
        } catch (IllegalArgumentException ex) {
            System.out.println("strict-consumption=INVALID");
        }

        DecimalFormat germanDecimal =
                (DecimalFormat) NumberFormat.getNumberInstance(
                        Locale.GERMANY);
        germanDecimal.setParseBigDecimal(true);
        BigDecimal exactLocalized =
                (BigDecimal) parseWhole("1.234,56", germanDecimal);
        System.out.println("localized-decimal=" +
                exactLocalized.toPlainString());

        BigDecimal exactMachine = new BigDecimal("1234.56");
        System.out.println("machine-decimal=" +
                exactMachine.toPlainString());
        System.out.println("decimal-sum=" +
                new BigDecimal("0.10")
                        .add(new BigDecimal("0.20"))
                        .toPlainString());

        System.out.println("format-us=" + us.format(1234.56));
        System.out.println("format-de=" + de.format(1234.56));
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac LocaleNumberParsingDemo.java
java LocaleNumberParsingDemo
```

Stdout on JDK 17+ with standard US/German locale data:

```text
machine=1234.56
scientific=1000.0
hex-float=3.0
whitespace=2.5
comma-machine=INVALID
underscore-machine=INVALID
overflow-infinite=true
nan=true
locale-us=1234.56
locale-de=1234.56
locale-same=true
prefix=123,consumed=3
strict-consumption=INVALID
localized-decimal=1234.56
machine-decimal=1234.56
decimal-sum=0.30
format-us=1,234.56
format-de=1.234,56
```

**Note on locale providers:** symbol/grouping data can be extended via the JDK's locale/provider system. The program pins `Locale.US` and `Locale.GERMANY` to avoid depending on the default locale, but in environments configured with custom providers, verify actual output rather than tying every symbol variant to one general assumption.

### Explaining the output

1. `machine`, `scientific`, and `hex-float` show Java's floating-point parser handling locale-independent syntax, including exponents and hexadecimal floats.
2. `comma-machine=INVALID` because `Double.parseDouble` does not automatically accept grouped digits `1,234.56`; `_` is also rejected in runtime strings.
3. `overflow-infinite=true` proves syntactically valid parsing **does not mean a finite value**.
4. The two US/German localized numbers represent the same value with different text.
5. `prefix=123,consumed=3` shows a parser can accept **a leading portion** and stop; `parseWhole` rejects it because the entire input was not consumed.
6. `setParseBigDecimal(true)` returns `BigDecimal` for the finite German string, preserving decimal **1234.56** without going through `double`.
7. `decimal-sum=0.30` shows `BigDecimal` preserves exact decimal digits and `scale` of the sample data.

## 11. Common errors and fixes

| Error/misconception | Why it is wrong | How to handle |
| --- | --- | --- |
| Assuming `Double.parseDouble` uses the default locale | It uses its own grammar and does not switch decimal points automatically | Use NumberFormat if input is localized |
| Parsing `"1,5"` with `Double.parseDouble` | Comma is not an accepted decimal point | Choose an appropriate locale/parser |
| Using NumberFormat without passing a locale | Output depends on system configuration | Pass Locale explicitly |
| Assuming parse(String) consumes the whole string | It can match a valid prefix and stop | Use ParsePosition and check index |
| Assuming ParsePosition guarantees all grouping is properly formatted | Locale parsers can be lenient | Add pattern/grammar validation |
| Casting `(Double) numberFormat.parse(text)` | The resulting Number may be a Long | Use Number, or configure BigDecimal |
| Calling `new BigDecimal(number.doubleValue())` after locale parsing | Introduces binary rounding error into BigDecimal | Parse directly with setParseBigDecimal(true) |
| Treating `Double.parseDouble("1e309")` as finite input | Result is Infinity despite valid syntax | Check Double.isFinite |
| Parsing money into double | Can lose decimal exactness | BigDecimal + scale/RoundingMode |
| Manually replacing all dots/commas | Easily changes numeric meaning or accepts invalid formats | Use the exact locale and a grammar contract |
| Assuming shared formatters are thread-safe | NumberFormat/DecimalFormat hold mutable state | Create separate instances; avoid sharing mutable ones |
| Using UI-formatted strings as API payloads | Formats include locale-specific grouping and rounding | Use a fixed machine number schema |
| Treating NaN/Infinity as valid BigDecimals | BigDecimal does not represent them | Explicit validation and type rejection |

## 12. Self-practice exercises

1. **Comparing two parsers.** For `"1,234.56"` and `"1.234,56"`, test `Double.parseDouble`, US `NumberFormat`, and German `NumberFormat`. Does each case consume the entire string? Conclude only after inspecting `ParsePosition`.
2. **Strings with trailing text.** Parse `"42kg"` with `NumberFormat.parse(String)` and with `parseWhole`. Why can one approach accept 42 while the other must reject it?
3. **Java syntax.** Predict the behavior of `Double.parseDouble("1e3")`, `Double.parseDouble("0x1.8p1")`, `Double.parseDouble("1_000")`, and `Double.parseDouble("NaN")`.
4. **Finite numbers.** Write a method accepting machine numbers and rejecting NaN, Infinity, and values outside `[-1000, 1000]`. Why is catching NumberFormatException insufficient?
5. **Locale and money.** Create a currency/amount parser for `Locale.GERMANY`, enable `setParseBigDecimal(true)`, and compute tax with `BigDecimal`. Choose scale/RoundingMode according to a specific contract.
6. **Grouping constraints.** Design a US validator that accepts `"1234.56"` or `"1,234.56"` under three-digit grouping rules, yet rejects `"12,34.56"`. Why is consuming the whole string insufficient to prove grouping validity?
7. **Internationalization.** Try a locale whose grouping separator is neither a comma nor a dot. Why should you not strip all whitespace indiscriminately?
8. **API and UI.** Design a storage pipeline: localized input → BigDecimal → domain data → localized format; identify which step is allowed to round.
9. **Automated tests.** Write unit tests for `parseWhole` with null, empty string, invalid string, number with suffix, valid US/German numbers, and trailing-text cases.
10. **Protocols.** A machine CSV file specifies a decimal dot and no grouping. Why does passing `Locale.getDefault()` to a parser cause the file to be interpreted differently when run on another machine?

## 13. Practical checklist

- Ask first: **is this fixed technical data or localized display/input text?**
- For machine data: use `Double.parseDouble`, `Float.parseFloat`, or `BigDecimal(String)` with protocol grammar validation.
- For regional user data: use `NumberFormat`/`DecimalFormat` with an **explicit Locale**.
- Remember that `.`, `,`, grouping, and Unicode characters can change meaning across locales.
- With `NumberFormat`, **verify full string consumption** using `ParsePosition` when required; a parsed prefix result is not proof of valid input.
- If the grammar must be strict, add validators for grouping, signs, whitespace, digit counts, and accepted formats.
- Do not cast a `Number` result to `Double` without checking its type; if exact decimals are needed, use `DecimalFormat.setParseBigDecimal(true)`.
- Do not use `new BigDecimal(double)` after already parsing through double to "recover" a decimal string.
- Check `NaN`/`Infinity` and data range when parsing to float/double.
- For money or exact decimal data, keep `BigDecimal` and business rounding rules.
- Do not share mutable `DecimalFormat` instances across threads without proper protection.
- Test across multiple `Locale`s, including locales with different grouping characters, and with trailing invalid input.

**Conclusion:** `parseDouble`/`parseFloat` and `BigDecimal(String)` fit **locale-independent numeric syntax**, whereas `NumberFormat`/`DecimalFormat` serve **regional number strings**. Choosing the right parser, verifying complete input consumption, preserving required precision, and separating parsing from validation are the keys to avoiding silent arithmetic bugs in Java applications.