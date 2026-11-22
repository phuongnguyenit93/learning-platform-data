# BigDecimal.toPlainString() and Preserving the Desired Presentation

## 1. Goal: Outputting Decimal Numbers in Plain Form

`BigDecimal` in Java represents decimal numbers of arbitrary precision. A number may be output in **scientific notation** such as `1E+3` or `1.2E-7`. When you need a plain decimal string **without `E` or `e` representing an exponent**, use `toPlainString()`:

```java
BigDecimal large = new BigDecimal("1E+3");
BigDecimal small = new BigDecimal("1.2E-7");

System.out.println(large.toString());      // 1E+3
System.out.println(large.toPlainString()); // 1000
System.out.println(small.toString());      // 1.2E-7
System.out.println(small.toPlainString()); // 0.00000012
```

`toPlainString()` only **converts the value's representation into a `String`**. It does not round, does not modify the source `BigDecimal`, does not add thousands separators, and does not automatically choose the number of decimal digits according to business rules. "Preserving the desired presentation" requires clearly distinguishing between **value**, **scale**, **string conversion**, and **human-readable formatting**.

> Standalone illustrative snippets below use `import java.math.BigDecimal;` and, when rounding is involved, `import java.math.RoundingMode;`. Complete Java 17+ programs with compilation commands and outputs are in Section 7.

## 2. Three Ways to Convert BigDecimal to String

The three related methods serve different purposes:

| Method | Representation | Key Points to Remember |
| --- | --- | --- |
| `toString()` | Canonical string of `BigDecimal`, may use scientific notation. | The specification guarantees the string distinguishes the `unscaledValue` and `scale` pair; it can be used to reconstruct the same numeric state and scale via the `String` constructor. |
| `toPlainString()` | Plain decimal form, without exponents. | Easy to read or suitable where exponent-free decimal text is required; when scale is negative, parsing back from this string may **change the scale**. |
| `toEngineeringString()` | May use engineering notation, with the exponent (when present) being a multiple of 3. | Useful for engineering representation; not a substitute for `toPlainString()` if the output prohibits exponential notation. |

Examples:

```java
BigDecimal a = new BigDecimal("123.4500");
BigDecimal b = new BigDecimal("1E+3");
BigDecimal c = new BigDecimal("1.2E-7");

System.out.println(a.toString());      // 123.4500
System.out.println(a.toPlainString()); // 123.4500
System.out.println(b.toString());      // 1E+3
System.out.println(b.toPlainString()); // 1000
System.out.println(c.toString());      // 1.2E-7
System.out.println(c.toPlainString()); // 0.00000012
```

For many ordinary values, `toString()` and `toPlainString()` can be identical. The difference becomes prominent when the object has a **negative scale** or a value small enough for `toString()` to choose scientific notation under `BigDecimal`'s representation rules.

`String.valueOf(bigDecimal)` and string concatenation such as `"value=" + bigDecimal` invoke the `toString()` representation via object-to-string conversion. If the specific requirement is **no exponent**, call `toPlainString()` explicitly.

## 3. Why Do E+3 or E-7 Appear? The Role of Scale

`BigDecimal` is defined by an integer without a decimal point (*unscaled value*) and an integer `scale`:

```text
value = unscaledValue × 10^(-scale)
```

Examples:

| Initialization | Numeric Value | `scale()` | `toString()` | `toPlainString()` |
| --- | --- | ---: | --- | --- |
| `new BigDecimal("12.3400")` | 12.3400 | 4 | `12.3400` | `12.3400` |
| `new BigDecimal("1E+3")` | 1000 | -3 | `1E+3` | `1000` |
| `new BigDecimal("1.2E-7")` | 0.00000012 | 8 | `1.2E-7` | `0.00000012` |
| `new BigDecimal("0.00")` | 0 | 2 | `0.00` | `0.00` |

`scale` is not the number of significant digits (*precision*). It specifies the position of the decimal point relative to `unscaledValue`. Scale **can be negative**: `1E+3` represents `1 × 10³` and has a scale of `-3`. When converting to plain form, `toPlainString()` writes out all the zeros to produce `1000`.

With a non-negative scale, `toPlainString()` prints the decimal point at the appropriate position, including trailing zeros dictated by the scale; for example, `12.3400` remains `12.3400`. This is how you preserve the **decimal representation already held in the object** when you need to display the exact number of fractional digits currently stored.

This differs from recovering the **exact original input string**: `BigDecimal` does not store every character, `+` sign, leading zeros, or exponential style from the original text.

## 4. toPlainString() Does Not Round and Does Not Fix Decimal Places

Compare three distinct needs:

1. **No exponent:** `value.toPlainString()`.
2. **Force the result to have exactly two digits after the decimal point:** first call `value.setScale(2, roundingMode)`, and only then call `toPlainString()`.
3. **Human-friendly display with grouping separators, locale-specific decimal separators, or currency symbols:** use a formatter like `NumberFormat` or `DecimalFormat` with the appropriate `Locale` and rounding rules.

Example:

```java
BigDecimal amount = new BigDecimal("12.3");

System.out.println(amount.toPlainString());           // 12.3
System.out.println(amount.setScale(2).toPlainString()); // 12.30
System.out.println(amount.toPlainString());           // 12.3
```

Here `setScale(2)` increases the scale from 1 to 2, so no rounding is required. The method returns a **semantically new `BigDecimal` result**; the original `amount` object does not change because `BigDecimal` is immutable. You should not assume the JVM always allocates a physically different reference, especially when the requested scale already matches.

If reducing the scale requires discarding non-zero digits, the `setScale(int)` overload will throw `ArithmeticException`. When business logic permits rounding, specify `RoundingMode` explicitly:

```java
BigDecimal raw = new BigDecimal("12.345");

System.out.println(raw.toPlainString()); // 12.345
System.out.println(
        raw.setScale(2, RoundingMode.HALF_UP).toPlainString()
); // 12.35
```

**Do not round accidentally during the presentation step.** `toPlainString()` itself does not change the value; the `setScale(2, HALF_UP)` call actively applied the rounding rule. For currency, taxes, statistics, or persisted data, clearly define when and how rounding happens according to the business contract.

## 5. "Preserving Presentation" Has Multiple Levels

You must determine precisely what you want to preserve:

### 5.1. Preserving Mathematical Numeric Value

The two strings `1E+3` and `1000` describe the same number. Under `BigDecimal.compareTo()` numeric comparison, they are equal:

```java
BigDecimal scientific = new BigDecimal("1E+3");
BigDecimal plain = new BigDecimal("1000");

System.out.println(scientific.compareTo(plain)); // 0
```

If the protocol only requires an exact decimal value and forbids exponents, `toPlainString()` may be appropriate.

### 5.2. Preserving Existing Scale When Scale Is Non-Negative

`new BigDecimal("12.3400").toPlainString()` yields `"12.3400"`; both trailing zeros still appear. The value `new BigDecimal("12.34")` only prints `"12.34"` because its scale is 2, not 4. `toPlainString()` reflects the existing representation state and **does not restore** zeros that an earlier processing step removed.

If two decimal places must always be printed, produce an object with scale 2 using the appropriate rule before outputting.

### 5.3. Preserving the Exact User-Entered Text

`BigDecimal` does not store a verbatim copy of the source string. For example:

```java
BigDecimal x = new BigDecimal("00012.300");
System.out.println(x.toPlainString()); // 12.300
```

The leading zeros are gone. Similarly, notations like `+12.30`, `12.30`, and various exponential formats are normalized when constructing `BigDecimal`. If the product requirement is to **store the exact string the user entered** (such as audit records, orders with original text, or digitally signed text fields), you must store `String originalInput` separately while parsing it into `BigDecimal` for calculations when needed.

Example with negative zero: `new BigDecimal("-0.00").toPlainString()` outputs `"0.00"`, not preserving the input's negative sign. `BigDecimal` represents the value 0 and does not preserve "negative zero" as a separate semantic component of decimal data.

### 5.4. Preserving Negative Scale Across String Round-Trips

This is a case that is **easily overlooked**:

```java
BigDecimal original = new BigDecimal("1E+3");     // scale = -3
String plainText = original.toPlainString();      // "1000"
BigDecimal restored = new BigDecimal(plainText);  // scale = 0

System.out.println(original.scale());           // -3
System.out.println(restored.scale());           // 0
System.out.println(original.equals(restored));  // false
System.out.println(original.compareTo(restored)); // 0
```

The two objects are equal in **numeric value**, but `equals()` returns `false` because `BigDecimal.equals()` considers both representation and scale. You should not use `toPlainString()` as a *round-trip* string when the data contract requires preserving **negative scales as well**.

Conversely:

```java
BigDecimal original = new BigDecimal("1E+3");
BigDecimal restored = new BigDecimal(original.toString());

System.out.println(original.equals(restored)); // true
```

`toString()` is designed as a one-to-one canonical representation of the unscaled value and scale pair, making it ideal for serializing to a string and restoring a `BigDecimal` with the same representation. Therefore, choosing an output method should stem from whether the requirement is **exponent-free display** or **preserving BigDecimal data during transmission/storage**.

## 6. Impact of stripTrailingZeros() and Pre-Output Conversions

`stripTrailingZeros()` removes removable trailing zeros without changing the numeric value, then returns a `BigDecimal`. It can change the scale to **negative**:

```java
BigDecimal amount = new BigDecimal("1000");
BigDecimal stripped = amount.stripTrailingZeros();

System.out.println(amount.toPlainString());   // 1000
System.out.println(stripped.toString());      // 1E+3
System.out.println(stripped.toPlainString()); // 1000
System.out.println(stripped.scale());         // -3
```

If `toString()` is called after `stripTrailingZeros()`, scientific notation can appear even though the original input was an ordinary number. `toPlainString()` produces an exponent-free form, but **does not restore the scale and trailing zeros of the original representation** that `stripTrailingZeros()` removed.

Example:

```java
BigDecimal original = new BigDecimal("12.3400");
BigDecimal stripped = original.stripTrailingZeros();

System.out.println(original.toPlainString()); // 12.3400
System.out.println(stripped.toPlainString()); // 12.34
```

If the display contract demands exactly four decimal places, do not call `stripTrailingZeros()` before outputting; or apply `setScale(4)` when increasing the scale is intentional. You should define one place responsible for "normalizing numbers for storage" and another for "formatting numbers for viewing," rather than mixing these operations across multiple layers.

### Avoid Creating BigDecimal from double When Exact Decimals Are Required

`new BigDecimal(0.1)` represents the exact binary value of the `double` literal `0.1`, which is an approximation of the decimal number 0.1. `toPlainString()` **cannot fix** that input discrepancy. Prefer:

```java
BigDecimal fromText = new BigDecimal("0.1");
BigDecimal fromDouble = BigDecimal.valueOf(0.1);

System.out.println(fromText.toPlainString());   // 0.1
System.out.println(fromDouble.toPlainString()); // 0.1
```

`BigDecimal.valueOf(double)` uses the string representation of `double` to construct the `BigDecimal`; this is usually suitable for literals like `0.1`, but cannot recover decimal digits already lost by earlier `double` arithmetic.

## 7. Standalone Runnable Java 17+ Program

Save all the following code as `BigDecimalPlainStringDemo.java`:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class BigDecimalPlainStringDemo {
    public static void main(String[] args) {
        BigDecimal thousand = new BigDecimal("1E+3");
        BigDecimal tiny = new BigDecimal("1.2E-7");

        System.out.println("thousand toString = " + thousand.toString());
        System.out.println("thousand plain = " + thousand.toPlainString());
        System.out.println("tiny toString = " + tiny.toString());
        System.out.println("tiny plain = " + tiny.toPlainString());

        BigDecimal entered = new BigDecimal("12.3400");
        System.out.println("entered plain = " + entered.toPlainString());
        System.out.println("stripped plain = "
                + entered.stripTrailingZeros().toPlainString());

        BigDecimal oneDecimal = new BigDecimal("12.3");
        System.out.println("one decimal = " + oneDecimal.toPlainString());
        System.out.println("two decimals = "
                + oneDecimal.setScale(2).toPlainString());

        BigDecimal rounded = new BigDecimal("12.345");
        System.out.println("rounded two decimals = "
                + rounded.setScale(2, RoundingMode.HALF_UP)
                         .toPlainString());

        BigDecimal fromPlain = new BigDecimal(thousand.toPlainString());
        BigDecimal fromCanonical = new BigDecimal(thousand.toString());
        System.out.println("original scale = " + thousand.scale());
        System.out.println("plain round-trip scale = " + fromPlain.scale());
        System.out.println("plain equals original = "
                + thousand.equals(fromPlain));
        System.out.println("canonical equals original = "
                + thousand.equals(fromCanonical));
        System.out.println("same numeric value = "
                + (thousand.compareTo(fromPlain) == 0));
    }
}
```

Compile and run from the directory containing the file:

```bash
javac BigDecimalPlainStringDemo.java
java BigDecimalPlainStringDemo
```

Expected output:

```text
thousand toString = 1E+3
thousand plain = 1000
tiny toString = 1.2E-7
tiny plain = 0.00000012
entered plain = 12.3400
stripped plain = 12.34
one decimal = 12.3
two decimals = 12.30
rounded two decimals = 12.35
original scale = -3
plain round-trip scale = 0
plain equals original = false
canonical equals original = true
same numeric value = true
```

Compare the first part to see the benefit of `toPlainString()` with exponents; the middle part shows trailing zeros being kept or removed depending on the **current scale**; the last part proves that an exponent-free decimal text version can **lose negative scale information** when read back, even though it preserves the numeric value.

## 8. Locale Display, Currency, and Data Exchange

### 8.1. When Is a Plain String Appropriate?

`toPlainString()` is useful when the target requires a basic ASCII decimal number:

- Values placed in a text file or a decimal field that mandates **no exponents**.
- Decimal strings exchanged with systems that read a period as the decimal separator and do not require grouping separators.
- Technical messages where viewing all decimal digits is preferred over scientific notation.

However, you must check the target system's contract: some places accept exponential notation, some enforce a fixed scale, and some limit digit count or length. `toPlainString()` does not guarantee meeting all those constraints.

### 8.2. User Interfaces Usually Need a Formatter

For example, if you want to display `1234.50` using the German convention of a dot for grouping and a comma for the decimal separator:

```java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.util.Locale;

public class LocaleNumberDemo {
    public static void main(String[] args) {
        BigDecimal amount = new BigDecimal("1234.50");

        NumberFormat formatter = NumberFormat.getNumberInstance(Locale.GERMANY);
        formatter.setMinimumFractionDigits(2);
        formatter.setMaximumFractionDigits(2);

        System.out.println(amount.toPlainString());
        System.out.println(formatter.format(amount));
    }
}
```

Save as `LocaleNumberDemo.java`, then run `javac LocaleNumberDemo.java` and `java LocaleNumberDemo`. With this data and `Locale.GERMANY` on Java 17+, the output is:

```text
1234.50
1.234,50
```

The difference here is **locale presentation rules**, not a change to the value inside `BigDecimal`. `NumberFormat` may round to fit the display digit limits; if there are specific business requirements for rounding, configure and test the appropriate policy rather than relying solely on the formatter's defaults. For currency, use a currency formatter when currency symbols, symbol placement, and display rules are needed; do not manually concatenate currency symbols onto a plain string if localization is required.

### 8.3. Storage and Serialization: Choose by Contract

If you want to preserve **both unscaled value and scale**, `toString()` has round-trip properties suitable for `BigDecimal` via the `String` constructor. You can also explicitly store `unscaledValue` alongside `scale` when designing a specialized data structure.

If the contract requires **output without exponential notation** and only cares about numeric value, `toPlainString()` is usually reasonable. When reading it back, do not assume `equals()` holds for numbers that previously had a negative scale; compare with `compareTo() == 0` if numeric equality is the actual goal.

For JSON, databases, XML, or APIs, verify the data type, the library's serialization rules, and specific length/precision/scale limits. You should not assume every serializer calls `toPlainString()`, or that every system stores trailing zeros and scale the same way Java does.

### 8.4. Performance and Length Considerations

A `BigDecimal` holding a very large exponent can still be represented as a compact scientific string. When converted to plain form, many zeros must be materialized directly.

```java
BigDecimal large = new BigDecimal("1E+10");
System.out.println(large.toPlainString()); // 10000000000
```

With an excessively large exponent, a plain string can become unusually long, consume significant memory, and violate payload size limits. Before outputting untrusted input data, constrain the numeric range, scale, length, or use another representation as required by the protocol. Do not call `toPlainString()` unconditionally on data with unbounded exponents.

## 9. Usage Patterns and Common Pitfalls

### Pattern 1 — Exponent-Free Decimal Text with Exactly Two Decimal Places

When the contract requires exactly 2 digits after the decimal point and specifies `HALF_UP`:

```java
static String toPlainTwoDecimals(BigDecimal value) {
    return value.setScale(2, RoundingMode.HALF_UP).toPlainString();
}
```

This is an **illustrative method** that must be placed inside a class with the corresponding `BigDecimal` and `RoundingMode` imports; the `HALF_UP` policy and scale 2 are just examples. Some business domains have their own rounding rules or forbid rounding the original value.

If losing digits is strictly forbidden, you can substitute `value.setScale(2, RoundingMode.UNNECESSARY).toPlainString()`. If an input requires reducing scale and non-zero digits would be discarded, it will throw `ArithmeticException`, helping detect contract-violating data.

### Pattern 2 — Preserving the Exact Input Text

If the requirement is to keep every original character:

```java
String originalInput = "00012.300";
BigDecimal value = new BigDecimal(originalInput);

System.out.println(originalInput);        // 00012.300
System.out.println(value.toPlainString()); // 12.300
```

Store the original string separately; `BigDecimal` holds information for computation, **it is not a verbatim text archive**. Pay special attention to whitespace, plus signs, leading zeros, and locale separator conventions before parsing.

### Pattern 3 — Round-Trip Structure Preserving Scale

When the goal is to restore the exact `BigDecimal` object according to `equals()`, use `toString()` followed by `new BigDecimal(text)`, or store the two components `unscaledValue` and `scale`. Do not arbitrarily substitute plain text when negative scales may occur.

### Common Pitfalls

1. **Assuming `toPlainString()` rounds automatically:** it only outputs a string. To reduce digits, an explicit rounding operation is required.
2. **Assuming `toPlainString()` always has exactly two fractional digits:** the number of digits depends on the current scale. `12.3` stays `12.3`, and `12.3000` stays `12.3000` if the scale has not been changed.
3. **Assuming the resulting string always matches the verbatim input:** `"00012.300"` becomes `"12.300"`; original formatting is lost.
4. **Using `stripTrailingZeros()` before needing to keep the fractional digit count:** `12.3400` becomes `12.34`. This is an intentional representation change and the original trailing zeros cannot all be guessed back.
5. **Using `toPlainString()` for serialization that must preserve negative scale:** `1E+3` becomes `1000`, which parses back with scale 0 instead of -3.
6. **Using `new BigDecimal(double)` and thinking plain output fixes input error:** false; you must control number creation and math before converting to a string.
7. **Using `toPlainString()` for locale formatting:** it does not add thousands separators, choose a decimal comma, or display currency units.
8. **Using `equals()` when only numeric equality is needed:** `1E+3` and `1000` can have different scales; use `compareTo() == 0` for numeric comparison.
9. **Ignoring the size of plain strings:** numbers with large exponents can expand into huge numbers of zeros; enforce protocol limits before outputting.
10. **Confusing the string with the object:** `toPlainString()` returns a `String`; calling it does not modify or permanently format the source `BigDecimal`. To save presentation settings, store the string, formatter configuration, or formatting contract separately.

## 10. Self-Check Questions

**Question 1.** Why is `new BigDecimal("1E+3").toPlainString()` equal to `"1000"`?

**Answer:** `toPlainString()` represents the decimal without exponents. The value `1 × 10³` is written using ordinary digits.

**Question 2.** Why does `new BigDecimal("12.3400").toPlainString()` remain `"12.3400"`?

**Answer:** The object has scale 4. `toPlainString()` does not automatically drop trailing zeros or pick a different scale.

**Question 3.** What should you do if you want `"12.30"` from `new BigDecimal("12.3")`?

**Answer:** `value.setScale(2).toPlainString()`, because increasing the scale from 1 to 2 and adding zeros loses no precision.

**Question 4.** What if you need `"12.35"` from `new BigDecimal("12.345")` using the `HALF_UP` rule?

**Answer:** `value.setScale(2, RoundingMode.HALF_UP).toPlainString()`. Rounding to `12.35` takes place in `setScale()`.

**Question 5.** Does `new BigDecimal(new BigDecimal("1E+3").toPlainString())` satisfy `equals()` with the original?

**Answer:** No. The original has scale -3, whereas the one parsed from `"1000"` has scale 0. `compareTo()` still returns 0 because their numeric values are equal.

**Question 6.** When should `toString()` be preferred over `toPlainString()`?

**Answer:** When you need a canonical representation that can reproduce the exact unscaled value and scale via the string constructor, and the contract permits scientific notation.

**Question 7.** To display `"1.234,50"` according to German conventions, do you use `toPlainString()` or a formatter?

**Answer:** Use `NumberFormat` or `DecimalFormat` configured for `Locale.GERMANY`, with the appropriate decimal-digit and rounding policy.

**Question 8.** To save the exact input `"00012.300"`, is keeping only the `BigDecimal` sufficient?

**Answer:** No. You need to store the original input string separately if leading zeros or original signs/formatting symbols are data that must be preserved.

**Takeaway:** `toPlainString()` produces a **decimal string without scientific notation** from an existing `BigDecimal`. It preserves the numeric value but **does not automatically fix scale, round, apply locale formatting, or store input text verbatim**. If negative scale must be preserved during serialization, consider `toString()` or structured storage; if a specific number of display digits is required, apply `setScale()` under the proper rules before outputting.
