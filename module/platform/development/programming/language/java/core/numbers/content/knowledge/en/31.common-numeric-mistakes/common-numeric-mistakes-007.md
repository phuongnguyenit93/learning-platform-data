# Mistake: Creating `BigDecimal` from `double` When Input Requires Decimal Exactness

Certain values such as money, unit prices, tax rates, and measurements specified in decimal digits must retain **the exact entered value**. A common mistake in Java is receiving the string `"0.1"`, converting it to `double`, and only then creating a `BigDecimal`. By that point, the application may already have lost decimal information during conversion to binary floating point. `BigDecimal` cannot guess or reconstruct verbatim the number the user submitted.

This lesson distinguishes `new BigDecimal(double)`, `BigDecimal.valueOf(double)`, and `new BigDecimal(String)`; clarifies when each is appropriate, the consequences of going through `double`, how to control `scale`/rounding, and how to test exact input data in Java 17+.

## 1. Why Can't `double` Represent Every Decimal Number Exactly?

`double` in Java follows IEEE 754 binary64 binary floating point. Its ordinary finite values can be viewed as binary numbers with finite precision. Fractions whose denominators contain only powers of 2, such as `0.5` (1/2) or `0.25` (1/4), can be represented exactly. However, `0.1` (1/10) has no finite representation in binary, so it must be **rounded to the nearest representable `double` value**.

Example:

```java
double a = 0.1;
double b = 0.2;
System.out.println(a + b); // 0.30000000000000004
```

This output is not Java "adding randomly wrong"; it is the result of representation and rounding in binary arithmetic. `double` itself is very useful for many engineering and scientific problems with allowable error, yet it is **not a verbatim storage container for decimal digits**.

Two kinds of exactness must be kept separate:

- **Exactness of the existing binary value:** A specific `double` value is a well-defined binary rational number; it can be converted to the full decimal representation of **that exact value**.
- **Exactness of the original decimal number:** The string `"0.1"` must correspond to exactly 1/10, or the string `"1.2300"` must also preserve the fractional digit count per contract.

Once an input string is parsed into `double`, those two forms of information are no longer equivalent.

## 2. The Main Trap: `new BigDecimal(double)`

The constructor taking `double` creates a `BigDecimal` whose value is **exactly equal to the binary value that `double` actually represents**, not the short decimal value typically printed on screen:

```java
import java.math.BigDecimal;

BigDecimal fromDouble = new BigDecimal(0.1);
System.out.println(fromDouble.toPlainString());
```

Output:

```text
0.1000000000000000055511151231257827021181583404541015625
```

Here the constructor honors its contract: it stores the exact `double` value closest to 0.1. It was `double` itself that approximated 1/10 before the constructor was called. Therefore, this approach is **unsuitable when you want to keep the exact decimal `0.1`**.

Compare:

```java
BigDecimal expected = new BigDecimal("0.1");
BigDecimal actual = new BigDecimal(0.1);

System.out.println(actual.compareTo(expected) == 0); // false
```

`actual` does not equal `expected` in **numeric value**, not merely in `scale`. This can produce unexpected results in limit checks, payment reconciliation, equality tests, or money allocation.

Some values like `0.5` are represented exactly in binary64, so `new BigDecimal(0.5)` yields exact decimal `0.5`. However, do not generalize from one lucky example to use the `double` constructor for all decimal inputs.

## 3. Correct When Source Text Exists: `new BigDecimal(String)`

If the original data is already a decimal string, parse directly from the string:

```java
BigDecimal price = new BigDecimal("19.99");
BigDecimal rate = new BigDecimal("0.075");
BigDecimal value = new BigDecimal("0.1");
```

These values are created from the exact decimal digits in the string, without going through binary64 rounding. This constructor supports signs and valid decimal notation according to `BigDecimal` syntax; it does not automatically handle locale conventions, currency grouping separators, or unit symbols.

There is nothing special about **string literals**: strings read from HTTP bodies, configuration files, CSVs, or input fields are equally suitable if they are the original decimal representation and have been validated against the contract.

Example:

```java
BigDecimal left = new BigDecimal("0.1");
BigDecimal right = new BigDecimal("0.2");

System.out.println(left.add(right).toPlainString()); // 0.3
```

Do not write:

```java
BigDecimal wrong = new BigDecimal(Double.parseDouble("19.99"));
```

`Double.parseDouble` rounds to binary64 first, and then `BigDecimal` stores the exact **rounded value**. If the requirement is to read `19.99` exactly, parse directly with `new BigDecimal("19.99")`.

### Comparing Three Construction Approaches

| Construction | Input Received | What It Guarantees | When Appropriate |
| --- | --- | --- | --- |
| `new BigDecimal("0.1")` | Decimal string | Exact decimal value of the string, preserves representation scale | Source data requires exact decimal |
| `new BigDecimal(0.1)` | `double` | **Current binary `double` value** converted exactly to decimal | Need to inspect/store the exact binary64 value already held |
| `BigDecimal.valueOf(0.1)` | `double` | Converts via `Double.toString(double)` representation then creates decimal | When the input genuinely is only a `double` and you want its canonical display decimal |
| `new BigDecimal(Double.toString(d))` | Canonical string from a `double` | Value equivalent to the typical conversion path of `valueOf(d)` | When you want the conversion step from `double` explicit |

When the original source is a string, **do not pass through `double`** just to call `valueOf`.

## 4. What `BigDecimal.valueOf(double)` Fixes and What It Cannot Fix

`BigDecimal.valueOf(double)` is usually a better choice than `new BigDecimal(double)` **when the only data you genuinely have is a `double`**. It uses the canonical string representation of `Double.toString(double)`, the short decimal string that round-trips back to the same `double` value:

```java
BigDecimal a = new BigDecimal(0.1);
BigDecimal b = BigDecimal.valueOf(0.1);

System.out.println(b.toPlainString()); // 0.1
System.out.println(a.compareTo(b) == 0); // false
```

`valueOf` eliminates the long digit tail caused by the binary representation in the `0.1` example and produces decimal `0.1`. However, **it does not guarantee recovering the original decimal input** in all cases.

For example, both `"0.10000000000000001"` and `"0.1"` can be rounded by `Double.parseDouble` to the exact same `double` value. Once merged, `BigDecimal.valueOf` cannot tell which string appeared originally:

```java
String source = "0.10000000000000001";
double rounded = Double.parseDouble(source);

BigDecimal recovered = BigDecimal.valueOf(rounded);
BigDecimal original = new BigDecimal(source);

System.out.println(recovered.toPlainString()); // 0.1
System.out.println(original.toPlainString());  // 0.10000000000000001
```

In addition, if arithmetic has already been performed in `double`, `valueOf` records the decimal corresponding to **the binary64 result**:

```java
double computed = 0.1 + 0.2;
BigDecimal result = BigDecimal.valueOf(computed);

System.out.println(result.toPlainString()); // 0.30000000000000004
```

Converting after addition cannot turn a `double` result into an exact 0.3 decimal addition. For exact decimal arithmetic, convert to `BigDecimal` **before performing operations** and start from exact decimal source numbers.

### `valueOf` Also Does Not Preserve Original Text Formatting

`BigDecimal.valueOf(1.0)` is built from the `"1.0"` string of `Double.toString(1.0)`; it cannot distinguish whether the original input was `"1"`, `"1.0"`, `"1.00"`, or `"1.000"`. If the number of fractional digits carries business meaning, receive and preserve it from the original text or separate metadata; it cannot be recovered from a `double`.

## 5. Why Late Conversion Can Break a Decimal Contract

Consider an API receiving a tax rate or monetary amount from a user. If the pipeline is:

```text
"0.10000000000000001" (original decimal)
     ↓ Double.parseDouble
0.1 (approximate double, no longer remembers original string)
     ↓ BigDecimal.valueOf
0.1 (BigDecimal decimal)
```

the final result no longer represents all of the decimal information submitted. Two distinct decimal strings can produce the same `double`, so **no general reverse algorithm exists** to determine which string came first.

The accuracy-preserving pipeline:

```text
"0.10000000000000001" (original decimal)
     ↓ new BigDecimal(String)
0.10000000000000001 (BigDecimal)
     ↓ BigDecimal calculations
Decimal result per mathematical/rounding contract
```

Identifying where information is lost matters more than which constructor you call at the end of the pipeline. Even if the end result uses `BigDecimal`, check the types at **every preceding step**: JSON libraries, CSV parsers, DTO mappings, JDBC, intermediate calculations, or getters returning `double`.

## 6. `scale`, `precision`, and Equality: Understand Both Value and Representation

`BigDecimal` stores a decimal value as an unscaled integer together with a `scale`. Two values can be numerically equal while having different `scale`s:

```java
BigDecimal x = new BigDecimal("1.0");
BigDecimal y = new BigDecimal("1.00");

System.out.println(x.compareTo(y) == 0); // true
System.out.println(x.equals(y));         // false
System.out.println(y.scale());           // 2
```

`compareTo` compares **numeric value**. `equals` checks both **numeric value and scale**, so `"1.0"` and `"1.00"` are not equal under `equals`. `HashMap`/`HashSet` rely on `equals` and `hashCode`; `TreeMap`/`TreeSet` in natural order rely on `compareTo`, so this distinction also affects duplicate key detection.

When parsed directly from `"1.00"`, scale 2 is preserved. If parsed through `double`, information about the original fractional digit count may already have been lost.

Distinguish:

- **Value exactness:** does the exact decimal match the original quantity?
- **`BigDecimal.precision()`:** total number of significant digits in the unscaled integer.
- **`BigDecimal.scale()`:** number of digits to the right of the decimal point (power of 10 in the denominator); scale can be negative.
- **Business resolution:** for instance, a smallest unit of 0.01 or 0.001.
- **Display formatting:** decimal separator, grouping separator, trailing digit count, and locale.

Do not assume that a successfully constructed `BigDecimal` already satisfies business resolution or range constraints.

## 7. Rounding Contracts and Resolution Checks

If a monetary field is only allowed a resolution of 0.01, there are at least two policies:

**Policy rejecting values not exactly representable in two decimal places:**

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal amount = new BigDecimal("12.30")
        .setScale(2, RoundingMode.UNNECESSARY);
```

The value `"12.345"` causes `setScale(2, RoundingMode.UNNECESSARY)` to throw `ArithmeticException`, because rounding would be required to reach two digits. The value `"12.300"` converts cleanly to `"12.30"`: stripping trailing zeros **does not change numeric value**. This differs from a contract enforcing **strictly two-digit syntax in the input string**; format contracts require separate validation.

**Policy allowing rounding under an explicit rule:**

```java
BigDecimal rounded = new BigDecimal("12.345")
        .setScale(2, RoundingMode.HALF_UP);
// rounded = 12.35
```

`HALF_UP` is only one option; many problems require `HALF_EVEN`, regulatory rules, or rejecting all rounding. Always specify **when** rounding occurs (per line item, invoice total, export step, etc.) because rounding at different stages can yield different totals.

### `new BigDecimal(double, MathContext)` Does Not Recover the Input

You can specify a `MathContext` to round a value constructed from `double` to a given number of significant digits. However, the starting value is still the approximated binary64, so this is not a way to reliably reconstruct the original decimal string. `MathContext` specifies **precision and rounding policy**, not a tool to decode lost information.

If the application needs minor units as `long`, convert from the exact decimal and use an exact conversion:

```java
long cents = new BigDecimal("12.30")
        .movePointRight(2)
        .longValueExact(); // 1230
```

`movePointRight(2)` multiplies by 100 in decimal arithmetic; `longValueExact()` rejects non-integer remainders or values outside `long` range. Never substitute `longValue()` unless silent truncation of fractional parts or high bits is acceptable.

## 8. Complete Java 17+ Code: Comparing Inputs, Conversions, and Limits

Save the following program as **`BigDecimalFromDoubleDemo.java`**:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class BigDecimalFromDoubleDemo {
    static BigDecimal parseExactAmount(String text) {
        if (text == null) {
            throw new IllegalArgumentException("amount is required");
        }
        BigDecimal amount = new BigDecimal(text)
                .setScale(2, RoundingMode.UNNECESSARY);

        if (amount.signum() < 0) {
            throw new IllegalArgumentException("negative amount");
        }
        return amount;
    }

    public static void main(String[] args) {
        BigDecimal fromDouble = new BigDecimal(0.1);
        BigDecimal fromValueOf = BigDecimal.valueOf(0.1);
        BigDecimal fromText = new BigDecimal("0.1");

        System.out.println("ctor decimal = " + fromDouble.toPlainString());
        System.out.println("valueOf decimal = " + fromValueOf.toPlainString());
        System.out.println("text decimal = " + fromText.toPlainString());
        System.out.println("ctor equals numeric text = "
                + (fromDouble.compareTo(fromText) == 0));

        BigDecimal exactSum = new BigDecimal("0.1")
                .add(new BigDecimal("0.2"));
        System.out.println("exact sum = " + exactSum.toPlainString());
        System.out.println("double sum converted = "
                + BigDecimal.valueOf(0.1 + 0.2).toPlainString());

        String source = "0.10000000000000001";
        System.out.println("original = " + new BigDecimal(source).toPlainString());
        System.out.println("through double = "
                + BigDecimal.valueOf(Double.parseDouble(source)).toPlainString());

        BigDecimal scaled = new BigDecimal("1.00");
        System.out.println("scale = " + scaled.scale());
        System.out.println("numeric equal = "
                + (scaled.compareTo(new BigDecimal("1.0")) == 0));
        System.out.println("object equal = "
                + scaled.equals(new BigDecimal("1.0")));

        System.out.println("accepted amount = "
                + parseExactAmount("12.300").toPlainString());
        try {
            parseExactAmount("12.345");
            System.out.println("extra decimals = accepted");
        } catch (ArithmeticException ex) {
            System.out.println("extra decimals = rejected");
        }
        try {
            parseExactAmount("-0.01");
            System.out.println("negative = accepted");
        } catch (IllegalArgumentException ex) {
            System.out.println("negative = rejected");
        }

        long cents = parseExactAmount("12.30")
                .movePointRight(2)
                .longValueExact();
        System.out.println("cents = " + cents);
        System.out.println("half exact = " + new BigDecimal(0.5).toPlainString());
    }
}
```

Compile and run in the directory containing the file:

```bash
javac -encoding UTF-8 BigDecimalFromDoubleDemo.java
java BigDecimalFromDoubleDemo
```

Stdout:

```text
ctor decimal = 0.1000000000000000055511151231257827021181583404541015625
valueOf decimal = 0.1
text decimal = 0.1
ctor equals numeric text = false
exact sum = 0.3
double sum converted = 0.30000000000000004
original = 0.10000000000000001
through double = 0.1
scale = 2
numeric equal = true
object equal = false
accepted amount = 12.30
extra decimals = rejected
negative = rejected
cents = 1230
half exact = 0.5
```

Key explanations:

1. The `double` constructor produces the long, exact decimal representation of **binary64 0.1**, distinct from the textual decimal `0.1`.
2. `BigDecimal.valueOf(0.1)` yields decimal `0.1`, yet when `0.1 + 0.2` is added in `double` **before calling** `valueOf`, the result is still `0.30000000000000004`.
3. The string `"0.10000000000000001"` loses extra digits when passed through `Double.parseDouble`, whereas `new BigDecimal(source)` preserves the decimal value intact.
4. `"1.00"` and `"1.0"` are numerically equal yet differ under `equals` due to scale.
5. The business parser uses `setScale(2, UNNECESSARY)` to normalize values exactly representable in hundredths of a currency unit; it rejects `"12.345"` and negative numbers.
6. `BigDecimal.valueOf(0.5)` or `new BigDecimal(0.5)` does not exhibit the trap because 1/2 is represented exactly in binary; not all decimal fractions behave that way.

## 9. JSON, Database, and External Data Boundaries

**JSON:** A JSON number is decimal notation in text, but how the deserializer decodes it decides whether data is lost. If a serializer/deserializer routes a decimal JSON field through `double` before constructing `BigDecimal`, precision may already be lost. Configure the parser to read decimal numeric tokens directly into `BigDecimal` when the contract requires exactness. For input `{"amount": 0.10000000000000001}`, keeping a decimal type in the backend differs from using `double` as an intermediate step.

**JavaScript:** `Number` uses binary64. When JavaScript parses a JSON number into `Number`, it may not retain the exact decimal digits expected by the server. If the protocol requires preserving exact money, rates, or large integers, agree on a representation (such as **decimal strings** and a matching decimal library) between frontend and backend. Do not arbitrarily change a JSON number field to string before clients adopt the new schema.

**Database/JDBC:** SQL `DECIMAL`/`NUMERIC` is generally suitable for exact decimals within schema bounds. When reading decimal columns, use the `BigDecimal` mapping/getter; reading via `getDouble()` can round before conversion. Conversely, data stored in `FLOAT`/`DOUBLE` columns may already have been approximated on write, even if the application reads it into `BigDecimal`.

**CSV/Excel:** Numeric columns may have been entered, saved, or calculated as floating point in another tool. If the file already lost digits when saving binary64 values, parsing into `BigDecimal` during Java import **cannot recover the original source**. For CSV files containing raw decimal strings, parse directly from the text field and clearly specify decimal separator/locale.

**API integration:** If digits after the decimal point are part of the contract, document them explicitly in the JSON/CSV/DTO specification: unit, range, maximum scale, whether scientific notation is permitted, whether trailing zeros are allowed, and whether excess resolution is rounded or rejected. Both sides must apply the same parsing and validation rules.

## 10. Choosing the API Based on Data Origin

| Input Source | What to Do | Avoid |
| --- | --- | --- |
| User-entered decimal string | `new BigDecimal(text)` then validate range/scale | `Double.parseDouble(text)` first |
| Exact decimal constant | `new BigDecimal("0.1")` | `new BigDecimal(0.1)` |
| Already have a valid `double` from measurement | Consider `BigDecimal.valueOf(d)` if decimal per `Double.toString(d)` is desired | Assuming `valueOf` recovers original decimal text |
| Want to know the exact stored binary64 value | `new BigDecimal(d)` | Confusing with original decimal representation |
| Already-computed `double` result | Preserve its approximate meaning or recompute from decimal sources | Calling `valueOf` at the end and assuming exact calculation |
| Decimal with fixed resolution | `setScale(scale, UNNECESSARY)` to reject rounding, or explicit mode | `setScale(scale)` while ignoring exceptions/rounding |
| Money in integer minor units | Parse exact decimal → scale up → `longValueExact()` | Multiplying in `double` then casting to `long` |
| JSON/SQL decimal | Preserve direct decimal mapping across boundaries | Passing through an intermediate `double` |
| Input already an integer | `BigDecimal.valueOf(longValue)` or `new BigDecimal(BigInteger)` | Converting large integers to `double` first |

`BigDecimal.valueOf(long)` is a separate overload from `BigDecimal.valueOf(double)`: when the input is `long`, the integer value is converted **exactly**, without going through binary64. This is the right choice when an integer input needs decimal representation.

## 11. Testing to Catch Conversion Incidents

Test cases should be designed from **source strings and business domains**, not merely from the output of the same buggy parser.

| Test Case | How to Construct | What to Assert |
| --- | --- | --- |
| Fraction not exact in binary | `"0.1"` | `new BigDecimal("0.1")` keeps value; `new BigDecimal(0.1)` differs |
| Fraction exact in binary | `"0.5"` | `double` constructor happens to match |
| Decimal addition | `"0.1" + "0.2"` | `BigDecimal.add` on strings produces `0.3` |
| Binary64 addition converted afterward | `BigDecimal.valueOf(0.1 + 0.2)` | `0.30000000000000004` |
| Decimal info lost when parsing double | `"0.10000000000000001"` | Direct string parse preserves decimal |
| Different scales | `"1.0"` and `"1.00"` | `compareTo == 0` yet `equals == false` |
| Excess resolution | `"12.345"` with scale 2 | Rejected or rounded per contract |
| Trailing zeros | `"12.300"` with scale 2 | Normalized to `12.30` without changing value |
| Out-of-range negative | `"-0.01"` in non-negative field | Rejected after parsing |
| Invalid notation | `"12,34"` with non-locale parser | Does not assume comma decimal point |
| Value exceeding minor integer range | Cents exceeding `long` | `longValueExact()` throws |
| NaN/infinity values | `Double.NaN`, `Infinity` | Have no corresponding ordinary `BigDecimal` value |

If you must convert `BigDecimal` to `double`, check precision loss in the reverse direction as well. `bigDecimal.doubleValue()` can return an approximation or infinity for large enough inputs; if the contract forbids precision loss, never treat this conversion as harmless.

Integration tests should cover the end-to-end path: from JSON/CSV/database literals through DTOs, domain models, calculations, and serialized responses. If at any stage the input is converted to `double`, verify whether that is an intentional error-tolerating decision or a design bug.

## 12. Common Mistakes

1. **Using `new BigDecimal(0.1)` thinking the constructor keeps decimal 0.1.** The constructor actually stores the exact binary64 value closest to 0.1.
2. **Believing `BigDecimal.valueOf(d)` always recovers decimal input.** It relies on `Double.toString(d)`; if data was already rounded into `double`, original source info cannot be restored.
3. **Computing in `double` first, converting to `BigDecimal` later.** Earlier errors and rounding remain baked into the resulting decimal representation.
4. **Going string → `double` → `BigDecimal`.** Adds an unnecessary binary64 step that can lose digits.
5. **Confusing `compareTo` with `equals`.** Equal decimal values with different `scale`s differ under `equals`; conversely, values from the `double` constructor can differ numerically as well.
6. **Thinking `setScale` recovers decimal exactness.** Rounding may produce a number that looks right without proving the original digits.
7. **Using `BigDecimal.valueOf(1.0)` and expecting it to remember the entered string `"1.000"`.** `double` does not store textual formatting.
8. **Not specifying an error policy for extra fractional digits.** An API silently rounding can alter business values.
9. **Overlooking JSON/JDBC/front-end layers.** Even if Java uses `BigDecimal`, an intermediate layer using `double` can still lose decimal digits.
10. **Claiming `double` is wrong in every context.** That is also false: `double` is valuable in approximate computation. The mistake is using it **when the contract demands exact decimals from the input**.

## 13. Practical Rules to Apply

When reading decimal data that requires exactness, **preserve the decimal representation from the source and construct `BigDecimal` directly from strings or exact decimal types**. Only use `BigDecimal.valueOf(double)` when the source genuinely is a `double` and you want a decimal matching its canonical representation. Use `new BigDecimal(double)` when you want to inspect the exact existing binary value, not when reconstructing what a user typed in decimal.

After parsing, validate range, resolution, rounding, and `null` per contract. Perform arithmetic using `BigDecimal` APIs, avoid intermediate conversions through `double`, and use **exact** conversions when converting back to integer types. The most important thing is spotting the earliest step where information is lost; conversions added after that step cannot replace precision that is already gone.

### Official Documentation

- [`BigDecimal` — constructors, `valueOf`, scale, rounding](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html)
- [`Double` — `toString`, `parseDouble`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Double.html)
- [`RoundingMode`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/RoundingMode.html)
- [JLS §4.2.3 — Floating-point types and values](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.2.3)
