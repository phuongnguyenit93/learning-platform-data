# Do Not Use Human-Formatted Strings as the Default Data-Exchange Format

In Java, a **numeric value** and a **string presenting a numeric value** are not the same kind of data. For display, an application may use thousands grouping separators, language-specific decimal marks, currency symbols, rounded digit counts, or measurement units to make numbers easy for humans to read. However, if you use those **human-formatted strings** by default to write files, send API payloads, or integrate with other systems, the data can **be misread, fail to parse, or lose precision**.

```java
double amount = 1_234_567.89;

System.out.println(String.format(
        java.util.Locale.US, "%,.2f", amount));
// 1,234,567.89

System.out.println(String.format(
        java.util.Locale.GERMANY, "%,.2f", amount));
// 1.234.567,89

System.out.println(Double.toString(amount));
// 1234567.89
```

All three strings represent the same input `double`, yet the first two serve **humans in different locales**. The third is Java's stable, locale-independent `double` representation, better suited for certain **explicitly specified** text exchange contracts.

**Primary rule:** data exchanged between programs must have an explicitly defined **schema and machine format**. UI presentation formats (human display formats) should not become the default wire format simply because users see them.

## 1. Distinguishing value, presentation, and wire representation

Three common layers:

| Layer | Question to answer | Example |
| --- | --- | --- |
| **Internal value** | What type and value is the system computing on? | `long 1234567L`, `double 1234.5`, `BigDecimal("1234.50")` |
| **Human presentation** | Which locale is the user in, how many digits, which unit? | `"1.234,50"`, `"1,234.50"`, `"1 234,50 €"` |
| **Exchange data** | Under what exact schema will the receiver read it? | JSON number `1234.5`, JSON string `"1234.50"` with decimal rules, or binary int64 |

**Human formatting** is a transformation from a value into a string for display. It may round, insert grouping separators, swap decimal symbols, or add text. Once rounded for UI display, parsing back may not recover the pre-rounding value.

**Exchange format** must explicitly specify character set, data type, signedness, unit, fractional representation, schema version, special-value representation, and validation rules. This is a contract between sender and receiver, **not** a side effect of a machine's locale settings.

### Typical example

An application has the value `1234.5`:

```text
Internal double:             1234.5
English (US) display:        1,234.50
German (Germany) display:    1.234,50
Wire decimal text (example): 1234.5
```

If an API receives `"1.234,50"` while assuming dot-based decimals, it may reject it, parse only part of the string, or misinterpret it. If UI formatting accidentally becomes stored data, merely changing the server's or user's locale is enough to cause compatibility failures.

## 2. Grouping and decimal separators have no universal meaning

Commas and dots play different roles depending on locale.

| Value | US Example | Germany Example |
| ---: | --- | --- |
| 1234.5 with 2 fractional digits | `1,234.50` | `1.234,50` |
| 1234567.89 with 2 fractional digits | `1,234,567.89` | `1.234.567,89` |
| 1000 with grouping | `1,000` | `1.000` |

The string `"1,234"` is **ambiguous** without a locale: it can be read as one thousand two hundred thirty-four in the US system, or one point two three four in a decimal-comma system. The string `"1.234"` has the opposite ambiguity.

It is not just dots and commas: some locales use spaces, non-breaking spaces, or specialized Unicode characters as grouping separators. Currencies also have differing symbols and symbol-placement rules. Therefore, a simple regex stripping commas or dots is **not a safe international parser**.

### Formatting with `String.format`

```java
double value = 1_234_567.89;

String us = String.format(
        java.util.Locale.US, "%,.2f", value);
String de = String.format(
        java.util.Locale.GERMANY, "%,.2f", value);
```

In `%,.2f`-style formatting:
- `,` is `Formatter`'s **grouping flag**; the actual grouping character depends on locale.
- `.2` requests two digits after the decimal point in the display string.
- `f` requests fixed-point floating-point formatting.
- `Locale.US` or `Locale.GERMANY` determines the displayed characters.

The pattern `%,.2f` **does not mean output always uses commas for grouping and a dot for the decimal point**. It expresses presentation policy through the locale.

For protocols, only use `String.format` if the protocol **explicitly specifies** the locale, digit count, rounding rule, grouping, and parsing behavior. Do not use UI formatter output as the default content for JSON, CSV, or databases.

## 3. Damage from parsing presentation strings with machine parsers

`Double.parseDouble` understands Java floating-point syntax per its own contract, and **does not** accept locale-grouped numbers:

```java
double original = 1_234_567.89;
String shown = "1.234.567,89";

// Double.parseDouble(shown); // NumberFormatException.
double recovered = Double.parseDouble(
        Double.toString(original)); // Works.
```

`Double.parseDouble` is not a parser for all local display formats. `Integer.parseInt("1,000")` also fails even though `"1,000"` looks completely ordinary to a US user.

Distinguish:
- **`Double.parseDouble`/`Integer.parseInt`**: numeric parsers using Java's own syntax, unaware of locale grouping.
- **`NumberFormat.parse`/`DecimalFormat.parse`**: parsers following presentation and locale rules; suitable when receiving **human-entered input** under explicit rules.
- **Data-format parsers**: e.g., JSON parsers, CSV readers + field codecs, binary decoders; must follow the **data-exchange schema**.

If data is genuinely typed by a user in a locale, using `NumberFormat` can make sense. However, the parsed result should be **normalized into a numeric type** before moving on to processing and storage layers.

## 4. `NumberFormat.parse` can read a valid prefix and stop

A subtle trap: human-format parsers can **accept a leading portion of the string** without consuming all data. For example:

```java
java.text.NumberFormat german =
        java.text.NumberFormat.getNumberInstance(
                java.util.Locale.GERMANY);

java.text.ParsePosition position = new java.text.ParsePosition(0);
String input = "1.234,50junk";
Number number = german.parse(input, position);

System.out.println(number);              // 1234.5
System.out.println(position.getIndex()); // 8
System.out.println(input.length());      // 12
```

Here the string ends with `"junk"`. A non-null `Number` result **does not mean the entire input was valid**. To build a strict validator for user-entered data, check:

```java
boolean allConsumed = number != null
        && position.getIndex() == input.length();
```

Even after consuming the whole string, you must still check value range, returned numeric type, allowed characters, length limits, and business conditions. `NumberFormat` can use different parse modes such as `setParseIntegerOnly` or `DecimalFormat.setParseBigDecimal`; the returned `Number` is not guaranteed to be solely `BigDecimal` or `Double`.

**Do not use a regional presentation parser as a locale-unspecified wire-format validator.** When parsing depends on configuration, two machines/versions or two users can interpret the same string differently.

## 5. Defining wire formats with an explicit schema

An integer/floating-point exchange schema typically needs to specify:

1. **Value kind:** signed 32-bit, signed 64-bit, unsigned, fixed decimal, binary float, percentage, or identifier?
2. **Field type:** JSON number, JSON string, CSV text field, binary integer/float, database numeric column?
3. **Syntax:** `.` or `,` decimal mark, are exponents allowed, grouping allowed, leading `+` allowed?
4. **Precision and range:** minimum/maximum values, are infinite decimals allowed or fixed resolution?
5. **Rounding:** at which layer is rounding allowed, and under which `RoundingMode` if using decimals?
6. **Special values:** how are null, missing field, NaN, ±Infinity, ±0 represented?
7. **Unit:** is the value dollars, cents, seconds, milliseconds, meters, degrees, or dimensionless?
8. **Version compatibility:** when the schema changes units, parsing, types, or symbols, how do older clients detect it?
9. **Security limits:** input length, exponent magnitude, Unicode characters, validation, and error messages.

Example of a simple decimal text contract:

```text
Field: amount_decimal
Type on wire: JSON string
Grammar: optional ASCII '-' followed by digits, optional '.' and digits
Grouping: forbidden
Locale: fixed, not taken from client/server default
Precision/range: agreed by application schema
Example: "1234.50"
Java receiver: new BigDecimal(value) after validation
```

This is a **system-defined format**, not a mandatory universal standard for every API. What matters is that both sides agree on the same contract.

Another format might use a JSON number `1234.5` directly. That works if all receivers can preserve the required range and precision. There is no single optimal representation for every need.

## 6. `toString` and `parseXxx`: better choices than UI formatters when the contract matches

For signed integers:

```java
int i = -42;
long l = 9_000_000_000L;

String encodedInt = Integer.toString(i);  // "-42"
String encodedLong = Long.toString(l);    // "9000000000"

int decodedInt = Integer.parseInt(encodedInt);
long decodedLong = Long.parseLong(encodedLong);
```

These APIs do not add grouping, currency symbols, or switch decimal marks based on the default locale. They can be used in a **signed ASCII decimal schema** for `int`/`long` if the receiver agrees on syntax and range.

For bases other than 10:

```java
String hex = Integer.toString(255, 16);  // "ff"
int recovered = Integer.parseInt(hex, 16); // 255
```

`radix` must also be part of the contract. `Integer.toString(value,16)` does not add `0x`; `parseInt(text,16)` does not strip `0x`. Do not feed UI-prefixed strings into parsers that do not support that prefix.

### Signed and unsigned are two separate conventions

`Integer.toUnsignedString(-1)` returns `"4294967295"`, whereas `Integer.toString(-1)` returns `"-1"`. The strings differ even though the `int` bit pattern is identical. If the wire schema is unsigned 32-bit, the receiver must parse with `Integer.parseUnsignedInt` (or a wider numeric model) and know the value is unsigned.

For `long`, `Long.toUnsignedString` and `Long.parseUnsignedLong` express 64 bits in an unsigned sense. Do not emit a negative number in hex `"ffffffff"` and call a default signed parser, because it can exceed range and fail.

### `Double.toString` is a formatter for binary64 values, not currency

`Double.toString(double)` returns a **locale-independent** decimal floating-point representation for a binary64 value. For finite numbers, the string is designed to parse with `Double.parseDouble` back to the exact same `double` value.

```java
double sample = 0.1 + 0.2;
String text = Double.toString(sample);

System.out.println(text); // 0.30000000000000004
System.out.println(Double.parseDouble(text) == sample); // true
```

That preserves the **existing binary value**, not proving `0.1 + 0.2` is an exact decimal calculation. `Double.toString` also produces `"NaN"`, `"Infinity"`, and `"-Infinity"` for special values, which are **invalid as JSON numbers under the JSON standard**.

Therefore, in applications exchanging JSON, use a compliant **JSON serializer** with a policy for non-finite numbers; do not arbitrarily concatenate `Double.toString` to assemble JSON.

## 7. `BigDecimal`: preserving business-meaningful decimals

When data represents exact decimal numbers (such as monetary amounts, tax rates, or quantities in smallest units), `BigDecimal` is a common choice. It differs from `double` in that it can accurately represent decimals like `0.1` when constructed from a **decimal string**.

```java
java.math.BigDecimal a = new java.math.BigDecimal("0.1");
java.math.BigDecimal b = new java.math.BigDecimal("0.2");

System.out.println(a.add(b).toPlainString()); // 0.3
```

Do not construct `BigDecimal` from strings with grouping separators or altered decimal marks:

```java
// new BigDecimal("1.234,50"); // NumberFormatException.

java.math.BigDecimal amount =
        new java.math.BigDecimal("1234.50");

System.out.println(amount.toPlainString()); // 1234.50
System.out.println(amount.scale());         // 2
```

`BigDecimal.toPlainString()` does not use exponent notation; `BigDecimal.toString()` may choose exponent notation when appropriate:

```java
java.math.BigDecimal x = new java.math.BigDecimal("1E+7");
System.out.println(x.toString());      // 1E+7
System.out.println(x.toPlainString()); // 10000000
```

### Choosing `toString` or `toPlainString`?

- `toString()` is `BigDecimal`'s canonical representation that may use exponents, designed for representation/parsing and preserving scale information per the API definition.
- `toPlainString()` suits schemas that accept only decimal digits and a dot, **disallowing exponents**; however, plain form can grow very long when a number has a huge exponent.
- `stripTrailingZeros()`, `setScale(...)`, and rounding operations can alter scale or value, so apply them only when **the schema specifies**. Do not arbitrarily strip `"1234.50"` to `"1234.5"` if fractional digit count/scale carries meaning.

If preserving **scale** across a round trip is required, note that `toPlainString()` on `BigDecimal` values with negative scale may reconstruct the same numeric value with a different scale when parsed. Use `BigDecimal.toString` or store scale/representation explicitly when it is part of the contract. Do not treat `toPlainString` as a universal way to "keep all numeric metadata".

### `new BigDecimal(double)` differs from `new BigDecimal(String)`

`new BigDecimal(0.1)` expresses the exact **binary approximation** of `double 0.1`, so its decimal string can be very long. If the input is truly a decimal number typed by a user, prefer **retaining the valid original text** and creating `new BigDecimal("0.1")` instead of passing it through `double` first.

`BigDecimal.valueOf(0.1)` uses the canonical string representation of `double`, so it typically yields `BigDecimal("0.1")`, yet it **cannot recover digits or precision previously lost** in the source data. Review the source contract and handle rounding explicitly.

## 8. JSON: numeric tokens are not the same as display strings

JSON distinguishes **number** and **string**:

```json
{
  "quantity": 12,
  "ratio": 0.125,
  "amountDecimal": "1234.50",
  "accountCode": "00042"
}
```

This is an example of an **intentional schema**:
- `quantity` is a numeric integer.
- `ratio` is a JSON number using JSON's decimal syntax, with no locale grouping.
- `amountDecimal` is a JSON **string** containing exact decimal text per contract.
- `accountCode` is a string because leading zeros are part of the identifier.

In JSON, numeric tokens use `.` for the fractional part per the standard grammar. The string `"1.234,50"` can appear as a **string** but **does not become a JSON number just by sitting inside JSON**.

### `NaN` and `Infinity`

JSON has no standard numeric tokens for `NaN`, `Infinity`, or `-Infinity`. Therefore:

```java
double value = Double.NaN;
System.out.println(Double.toString(value)); // NaN
```

That `NaN` string is **not** a valid JSON number. When serializing floating-point values, define handling explicitly: reject them, use `null` under a clear contract, or use a schema-described status enum/string. Do not write `{"value": NaN}` expecting every JSON parser to read it.

### Receiver limitations

A valid `long` value can exceed the **contiguous exact integer** range of JavaScript `Number`, i.e., larger than `2^53` in magnitude. For example:

```java
long id = 9_007_199_254_740_993L;
System.out.println(Long.toString(id)); // 9007199254740993
System.out.println((double) id);       // 9.007199254740992E15
```

`double` cannot represent this integer accurately; many clients handling JSON numbers as binary64 share the same risk. For **IDs or large integers requiring absolute precision**, you can specify transmitting a **decimal string** and parsing into `long`/`BigInteger` on the receiving side, rather than an arbitrary JSON number.

However, **not every JSON number must be converted to a string**. Numeric tokens remain the natural choice for numbers within controlled range/precision, provided both sides use compatible models.

### Avoid hand-concatenating JSON strings

Do not concatenate:

```java
// Do NOT build a general JSON serializer like this:
String json = "{\\"value\\":" + Double.toString(value) + "}";
```

This snippet does not check NaN/Infinity, does not handle object string escaping, optional fields, schemas, or other serialization rules. Use your project's JSON library to serialize **typed values**, after policies for precision/finiteness/nulls are decided.

## 9. CSV and text files: each column needs a schema

CSV clearly illustrates the danger of mixing display with data. Suppose the column delimiter is a comma:

```text
id,quantity,price
42,3,1234.50
```

A US-formatted currency string `"1,234.50"` written directly into the `price` column contains **a comma that also serves as the column delimiter**. If you genuinely intend to store text containing commas, **CSV escaping/quoting** per the chosen CSV rules is required:

```text
id,quantity,price_display
42,3,"1,234.50"
```

Yet CSV quoting only protects **row/column structure**; it **does not guarantee** the receiver will understand the US decimal format. A stable schema usually specifies that the `price` column uses dot-decimal format, no grouping, and an explicit unit.

If an application needs to export CSV for **humans to open in a spreadsheet**, it may need formatting matching the user's locale and target tool. That is **human report export**, distinct from a **CSV integration feed** between services. Do not use the same export mode for both if their contracts conflict.

### Delimiters and numeric characters can conflict

In locales using a decimal comma, CSVs using a comma delimiter are even more prone to ambiguity. Some regions use semicolons as delimiters in spreadsheet text files. Do not assume every `.csv` file follows the same convention; know the schema, delimiter, encoding, quoting, and decimal parsing rules.

### Data that looks numeric but should not be converted to numeric types

Postal codes, document numbers, phone numbers, account numbers, and IDs with leading zeros are **identifier strings**, not operands for addition and subtraction. Passing `"00042"` through `Integer.parseInt` and `Integer.toString` leaves only `"42"`. Do not lose information by assuming "all-digit text must be stored as a number".

## 10. Database storage and inter-service messages

The same principle applies to databases:

- If a column represents an **integer**, use an integer type matching the range.
- If a column is a decimal needing exactness, use `DECIMAL`/`NUMERIC` with explicit precision/scale, and Java `BigDecimal` when appropriate for the driver/API.
- If a column is an identifier, use text or a semantically appropriate specialized type.
- If a UI wants to display currency, **format only at the presentation layer** once locale/language/rules are known.

Do not store `"1.234,50 €"` as the sole value of a money column just because the UI renders it that way: sorting, filtering, summing, converting units, and switching locales later will be far harder. Normalized data should separate **value, currency code, unit, and metadata** per schema.

When using JDBC, use typed setters/getters (`setLong`, `setBigDecimal`, etc.) matching the schema/driver, rather than calling `setString` with a human-formatted string and hoping the database interprets it correctly.

### Clearly separate data flows

```text
User input
       |
       v
Validation + parse per locale/input policy
       |
       v
Typed value: int / long / BigDecimal / double
       |                         |
       |                         +--> Wire codec per schema -> API/file/DB
       |
       +--> Locale-based formatter -> UI/report
```

Do not let the **Locale-based formatter** branch flow back into the **Wire codec** branch without a matching parse contract and exact validation.

## 11. Standalone runnable Java 17+ program

Save the file `HumanVsWireDemo.java`:

```java
import java.math.BigDecimal;
import java.text.DecimalFormatSymbols;
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;

public class HumanVsWireDemo {
    static String parseDoubleResult(String text) {
        try {
            return Double.toString(Double.parseDouble(text));
        } catch (NumberFormatException ex) {
            return "INVALID";
        }
    }

    public static void main(String[] args) {
        double amount = 1_234_567.89;

        System.out.println("Human US: "
                + String.format(Locale.US, "%,.2f", amount));
        System.out.println("Human DE: "
                + String.format(Locale.GERMANY, "%,.2f", amount));
        System.out.println("Machine double: "
                + Double.toString(amount));

        System.out.println("Parse human DE as double: "
                + parseDoubleResult("1.234.567,89"));
        System.out.println("Parse machine: "
                + parseDoubleResult(Double.toString(amount)));

        NumberFormat german =
                NumberFormat.getNumberInstance(Locale.GERMANY);
        ParsePosition pos = new ParsePosition(0);
        String untrusted = "1.234,50junk";
        Number parsed = german.parse(untrusted, pos);
        System.out.println("Lenient locale parse: " + parsed
                + "; consumed=" + pos.getIndex()
                + "/" + untrusted.length());

        BigDecimal exact = new BigDecimal("1234.50");
        System.out.println("Exact decimal plain: "
                + exact.toPlainString());
        System.out.println("Decimal scale: " + exact.scale());

        System.out.println("Scientific BigDecimal: "
                + new BigDecimal("1E+7").toString());
        System.out.println("Plain BigDecimal: "
                + new BigDecimal("1E+7").toPlainString());

        System.out.println("Exact decimal 0.1+0.2: "
                + new BigDecimal("0.1")
                    .add(new BigDecimal("0.2")).toPlainString());
        System.out.println("Double 0.1+0.2: "
                + Double.toString(0.1 + 0.2));

        long bigId = 9_007_199_254_740_993L;
        System.out.println("ID as long string: "
                + Long.toString(bigId));
        System.out.println("ID as double: "
                + Double.toString((double) bigId));

        System.out.println("NaN is finite? "
                + Double.isFinite(Double.NaN));
        System.out.println("Infinity is finite? "
                + Double.isFinite(Double.POSITIVE_INFINITY));
        System.out.println("German decimal code point: "
                + (int) DecimalFormatSymbols
                    .getInstance(Locale.GERMANY)
                    .getDecimalSeparator());
    }
}
```

Compile and run:

```bash
javac --release 17 HumanVsWireDemo.java
java HumanVsWireDemo
```

Stdout on JDK 17+ with corresponding locale data:

```text
Human US: 1,234,567.89
Human DE: 1.234.567,89
Machine double: 1234567.89
Parse human DE as double: INVALID
Parse machine: 1234567.89
Lenient locale parse: 1234.5; consumed=8/12
Exact decimal plain: 1234.50
Decimal scale: 2
Scientific BigDecimal: 1E+7
Plain BigDecimal: 10000000
Exact decimal 0.1+0.2: 0.3
Double 0.1+0.2: 0.30000000000000004
ID as long string: 9007199254740993
ID as double: 9.007199254740992E15
NaN is finite? false
Infinity is finite? false
German decimal code point: 44
```

`44` is the Unicode/ASCII code of the comma character (`,`). The `Lenient locale parse` line shows the parser read `"1.234,50"` yet **did not consume `"junk"`**; this is why `ParsePosition` must be checked if turning it into validation.

Illustrative locale-formatted outputs depend on the **JDK's locale data**; for long-lived protocols, all the more reason never to let locale settings become the wire contract. The `Double.toString`, `Long.toString`, and `BigDecimal` outputs demonstrate numeric strings that are not UI-formatted numbers.

## 12. Designing parsers/serializers along responsibility boundaries

### At the user input boundary

1. Determine the user's language/locale and input field type.
2. Display clear hints about decimal mark, grouping separator, and unit.
3. Parse using a parser suited for that input; check that the entire string was consumed.
4. Validate range, precision, scale, type, and nullability.
5. Turn the result into a **typed value** for use by the business layer.

### At the API/file output boundary

1. Choose JSON/CSV/protobuf/SQL/etc. per the real protocol, rather than picking `NumberFormat` output by intuition.
2. Document in the schema whether numbers are integer or decimal, units, null handling, and special numbers.
3. Use a standard serializer/codec or a strictly tested codec.
4. Preserve precision as required by the receiver; watch IEEE binary64 limits for large integers.
5. Validate when receiving back; **do not trust** that every string from another system is valid.
6. Test round trips and cross-compatibility across locales/JDKs/partners.

### At the display boundary

1. Receive **typed values** from business logic or APIs.
2. Choose user locale, currency style, rounding rule, and digit count.
3. Format into a readable string; never use it as a computation source.
4. If the UI allows user editing, parse back **through the input layer** with validation, instead of passing display strings across services as a "numeric value".

Separating these steps also makes testing easier: codecs have correctness tests, business logic has arithmetic tests, and UI formatting has locale tests without impacting the wire protocol.

## 13. Special cases that must be explicitly specified in the contract

### 13.1. Rounding for display

`String.format(Locale.US,"%.2f",value)` can shorten displayed fractional digits to two. If the original value had more digits, the display string has **lost information**. Do not re-parse it to store in place of the original value unless business logic genuinely wants rounding at that step.

For example, `1234.567` displays as `"1,234.57"` with grouping and 2 fractional digits; parsing back `1234.57` cannot restore `1234.567`.

### 13.2. Negative zero, `Infinity`, and `NaN`

In `double`, there are `-0.0` and `+0.0`, along with `NaN`/`±Infinity`. A UI formatter may handle or display them according to regional policy. In standard JSON numbers, NaN/Infinity values are invalid; signed zero may need semantic checks on the receiving end. If these special states matter, **the schema must define them separately**, rather than merely using `toString` output.

### 13.3. Precision and exponents

A JSON number can contain exponent notation, though the receiver may convert it into binary64, `BigDecimal`, or another numeric type. Use `BigDecimal.toPlainString` when the contract forbids exponents, while capping magnitude/length to prevent generating huge strings from untrusted exponent values.

### 13.4. Units and percentages

The UI string `"12.5%"` is a human-readable representation: the real number in the system might be `0.125`, `12.5`, or a value with unit "percent" depending on the contract. Simply stripping `%` does not determine how to normalize it. Similarly, `"1,2 km"` requires handling units, decimal locale, and km-to-m conversion rules, not merely calling `Double.parseDouble`.

### 13.5. Very large integer types

An identifier `9007199254740993` fits in Java `long` yet exceeds the contiguous exact range of JavaScript `Number`. A schema may keep it as a decimal JSON string. For Java-to-Java applications using exact `long` parsers and controlled ranges, a numeric token can also fit. **Choose based on the entire receiving ecosystem**, not just the sending Java code.

## 14. Test suite to have when building an exchange format

| Test group | Input/edge case | Expectation |
| --- | --- | --- |
| Locale US/DE | `1234.5` | UI format differs; wire format does not arbitrarily change |
| Parse human | `"1.234,50"` | Only matching locale parser accepts per policy |
| Parse machine | `"1234.50"` | Decimal codec accepts properly, no grouping |
| Weird grouping | `"1,23,4.5"` | Reject if schema disallows grouping |
| Trailing junk | `"1.234,50junk"` | Full-consumption validation must reject |
| Decimal precision | `"0.1"` plus `"0.2"` | `BigDecimal` gives exact `0.3` |
| Trailing zeros/scale | `"1234.50"` | Preserve scale if schema requires |
| Exponent | `"1E+7"` | Specify whether exponents are permitted |
| Large integer | `"9007199254740993"` | Preserved across all clients requiring exactness |
| Non-finite | NaN, Infinity | Never emit invalid JSON numeric tokens |
| Negative zero | `-0.0` | Specify whether sign must be distinguished |
| Identifiers | `"00042"` | Do not lose leading zeros |
| CSV quoting | `"1,234.50"` | Field does not split columns incorrectly |
| Unicode characters | NBSP, Unicode digits | Explicit accept/reject policy |
| Overly long values | Thousands of digits/large exponents | Resource bounds and error reporting |
| Default locale changed | Different JVM locale across hosts | Wire payload unchanged for same value/schema |

Tests should cover both **value round-trips** and **syntax**. If a lenient parser silently ignores weird characters, round-trips of valid values may still pass while malicious inputs get accepted.

## 15. Common mistakes

| Mistake | Consequence | Proper practice |
| --- | --- | --- |
| Calling `NumberFormat.getInstance().format(x)` and sending over API | Depends on default locale | Define separate wire codec and schema |
| Parsing locale output with `Double.parseDouble` | Fails on grouping/decimal comma | Parse UI with locale parser; wire with stable parser |
| Using `NumberFormat.parse` as a strict validator | May read only a prefix | Check `ParsePosition` consumed the whole string |
| Stripping all commas/dots to "normalize" | Can turn decimals into much larger numbers | Validate locale/grammar properly first |
| Sending money via `String.format("%.2f")` | Rounds and loses original data | `BigDecimal` + rounding policy at the right step |
| Thinking `Double.toString` preserves original decimals perfectly | Preserves only existing binary64 value | Keep decimal input as `BigDecimal`/`String` if needed |
| Creating `BigDecimal` from a `double` that already lost info | Cannot recover original decimal number | Parse from decimal text per schema |
| Sending `NaN` as a JSON number | Not standard JSON | Explicit non-finite policy before serialization |
| Sending large `long` IDs as JSON numbers ignoring JS clients | Can lose precision | Decimal string per schema when needed |
| Turning `"00042"` into a number to be "compact" | Loses leading zeros | Keep identifiers as `String` |
| Using `toPlainString` for huge exponents without limits | Strings can grow massive | Cap range/length when encoding |
| Using `String.format` output to store numeric DB columns | Strings can be misinterpreted | Use typed JDBC setters per schema |
| Treating CSV quoting as decimal parsing | Only protects field structure | Specify numeric column codec |
| Changing JVM locale changes API responses | Breaks compatibility and tests | Do not use default locale in wire layer |
| Omitting unit and scale | Receiver misinterprets numeric meaning | Schema must specify unit/currency/scale clearly |
| Using the same formatter for UI and integration | Mixes two contract types | Separate presentation formatters from serializers |

## 16. Self-check questions

1. Why can `"1,234.50"` and `"1.234,50"` display the same value yet should not be used as a locale-unspecified wire format?
2. What does `Double.parseDouble("1.234.567,89")` produce? To accept German user input, which API is relevant?
3. Why can calling `NumberFormat.parse` without checking `ParsePosition` let `"1.234,50junk"` slip through?
4. How do `Integer.toString`/`Long.toString` and `NumberFormat` differ in purpose?
5. Does `Double.toString(0.1+0.2)` guarantee an exact decimal `0.3`, or does it merely preserve the existing `double` value?
6. Why is `new BigDecimal("1234.50")` better than parsing a grouped display string and passing it through `double` when exact decimals are required?
7. How do `BigDecimal.toString` and `toPlainString` differ when a value is created from `"1E+7"`?
8. Why is `NaN` a valid `double` state yet cannot be written directly as a standard JSON numeric token?
9. What problem does a `long` ID equal to `9007199254740993` have when the client uses JavaScript `Number`?
10. CSV uses commas to separate columns: if a field contains `"1,234.50"`, which step preserves column structure? Which step defines the numeric meaning of the field?
11. Why must a code `"00042"` usually be kept as `String` even though it consists only of digits?
12. What kind of values should the UI layer, business layer, and wire layer each hold?
13. In a decimal string schema, what must be documented regarding sign characters, radix, exponents, grouping, precision/scale, and units?
14. If a formatter rounds `1234.567` to `"1,234.57"`, can parsing it back recover the original number?
15. How do you test that changing `Locale.getDefault()` does not alter JSON/CSV integration payloads under the same schema?

## 17. Official references

- [Java SE 17 — `NumberFormat`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html): locale-based number formatting and parsing, grouping/precision options.
- [Java SE 17 — `DecimalFormat`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormat.html): decimal presentation patterns and parser properties.
- [Java SE 17 — `ParsePosition`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/ParsePosition.html): parser-consumed index and error info.
- [Java SE 17 — `Double`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html): `toString`, `parseDouble`, non-finite values, and binary64 rules.
- [Java SE 17 — `BigDecimal`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): `toString`, `toPlainString`, scale, exact decimals.
- [RFC 8259 — The JavaScript Object Notation (JSON) Data Interchange Format](https://www.rfc-editor.org/rfc/rfc8259): JSON number grammar, interoperability, non-finite values disallowed.
- [Java SE 17 — `Formatter`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Formatter.html): grouping, precision, and locale symbols in presentation output.

**Conclusion:** Locale-formatted strings are well suited for **UIs and human reports**, not as a reliable default wire format. Exchange **typed values** through **stable schemas/serializers**; for decimals needing precision, specify decimal text and `BigDecimal`; for large `long` values, consider JS clients; for floating-point, define `NaN`/`Infinity` policies. Only at the display layer should you pick grouping, currency, decimal marks, units, and rounding suited for human readers.