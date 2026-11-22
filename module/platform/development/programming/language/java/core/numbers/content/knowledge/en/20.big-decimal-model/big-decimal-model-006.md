# BigDecimal: Constructors Taking `double` and Binary Representation Noise

In Java, `java.math.BigDecimal` enables **decimal** arithmetic with an unscaled value and a scale, without suffering binary rounding error on every addition, subtraction, and multiplication like `double`. However, **how you create a `BigDecimal` matters just as much as how you compute with it**. If the input is a `double` that already approximates the intended decimal number, the `new BigDecimal(double)` constructor will **preserve the exact binary value received**, including its slight offset, rather than guessing the decimal number the programmer meant.

```java
import java.math.BigDecimal;

BigDecimal fromDouble = new BigDecimal(0.1);
BigDecimal fromText = new BigDecimal("0.1");
BigDecimal fromFactory = BigDecimal.valueOf(0.1);

System.out.println(fromDouble);
// 0.1000000000000000055511151231257827021181583404541015625

System.out.println(fromText);    // 0.1
System.out.println(fromFactory); // 0.1
```

The long line is not "`BigDecimal` introducing new error". It is the **exact decimal spelling of the `double` value that was previously binary-quantized**. Understanding this helps prevent bugs when calculating money, reading decimal data, converting units, and putting numeric results into reports.

This lesson focuses on: the two number classes, the origin of binary noise, the contract of `BigDecimal(double)`, `BigDecimal.valueOf(double)`, `BigDecimal(String)`, scale/precision, cases with and without noise, effects on calculations and comparisons, rounding, limitations once data has passed through `double`, and safe ways to choose constructors.

## 1. Why Is `0.1` Not an Exact Decimal `double`?

`double` uses **IEEE 754 binary64**, consisting of sign, exponent, and significand bits represented in base **2**. Meanwhile, the literal `0.1` mathematically represents **one tenth**, i.e., `1/10`.

A decimal fraction can be represented finitely in binary only if, after reduction, its denominator is a power of 2. `1/10` has a factor of 5 in its denominator, so it **has no finite binary expansion**.

The Java compiler must pick a binary64 value close to `0.1`. The actual stored value is:

```text
0.1000000000000000055511151231257827021181583404541015625
```

This is the exact decimal value of the binary64 bit pattern chosen for the literal `0.1`, **not** the original "one tenth" at infinite precision.

### Data Flow Diagram

```text
Mathematical intent: 0.1  (1/10)
          |
          | Assign to double literal / variable
          v
Nearest binary64:    0.1000000000000000055511...
          |
          | new BigDecimal(double) preserves exact binary64 value
          v
BigDecimal:          0.1000000000000000055511...
```

**Key point:** `BigDecimal(double)` does not "intentionally add noise"; it takes an already-approximated input and converts that value **exactly** to a decimal number. The length of the string is a sign that the data source was originally binary64.

### Trying Other Fractions

| Mathematical value | Finite binary representation? | `new BigDecimal(double)` when given literal |
| --- | --- | --- |
| `0.5 = 1/2` | Yes | `0.5` |
| `0.25 = 1/4` | Yes | `0.25` |
| `0.125 = 1/8` | Yes | `0.125` |
| `0.1 = 1/10` | No | A long decimal string, slightly larger than 0.1 |
| `0.2 = 1/5` | No | A long decimal string |
| `0.3 = 3/10` | No | A long decimal string, depending on the chosen binary64 value |

**Not every `double` value produces a long string.** Many small integers, fractions with power-of-2 denominators, and certain other values have compact decimal representations. The worst mistake is assuming `new BigDecimal(double)` is always equivalent to `new BigDecimal("intended-value")`.

## 2. How Does `BigDecimal` Store a Value?

Conceptually, the numeric value of a `BigDecimal` is:

\[
\mathrm{value} = \mathrm{unscaledValue} \times 10^{-\mathrm{scale}}
\]

`unscaledValue()` returns a `BigInteger`; `scale()` returns an integer indicating the decimal point position. With these two parts, `BigDecimal` describes an exact decimal number without keeping a `double` inside.

Example:

```java
BigDecimal value = new BigDecimal("12.34");

System.out.println(value.unscaledValue()); // 1234
System.out.println(value.scale());         // 2
```

`1234 × 10^-2 = 12.34`.

With data from `new BigDecimal(0.1)`, the unscaled part is an integer with very many digits, and scale is larger because it must spell out the binary64 value exactly in base 10:

```java
BigDecimal fromDouble = new BigDecimal(0.1);

System.out.println(fromDouble.scale()); // 55
System.out.println(fromDouble.unscaledValue());
// 1000000000000000055511151231257827021181583404541015625
```

This explains why math on `BigDecimal`s created from `double` can carry along many decimal digits: they genuinely hold **decimal values with large precision/scale**, and BigDecimal operations by default on many operations attempt to preserve exact results relative to those operands.

### `precision` Is Not `scale`

- **Scale**: the negated decimal exponent (for positive scale, typically the number of digits after the decimal point).
- **Precision**: the number of digits in `unscaledValue` (ignoring sign), per the API contract.

```java
BigDecimal a = new BigDecimal("1.2300");
System.out.println(a.scale());     // 4
System.out.println(a.precision()); // 5

BigDecimal b = new BigDecimal("1.23");
System.out.println(b.scale());     // 2
System.out.println(b.precision()); // 3
```

Two values can be arithmetically equal while differing in scale. Therefore, when observing long strings from `new BigDecimal(double)`, examine both **numeric value** and **representation**; merely looking at the displayed digit count does not fix the root cause.

## 3. Contract of `new BigDecimal(double)`

The Oracle Java SE 17 API describes the constructor:

```java
public BigDecimal(double val)
```

It creates a `BigDecimal` whose value is equal to the exact **binary floating-point value of the `double` argument**. The smallest scale is chosen such that the value can be written as an integer times `10^-scale`.

```java
BigDecimal x = new BigDecimal(0.1);
System.out.println(x.toPlainString());
// 0.1000000000000000055511151231257827021181583404541015625
```

Consequences:
1. The constructor does **not** re-read the token `0.1` in source code to guess the programmer's intent.
2. The constructor does **not** use the shortened string from `Double.toString`.
3. It does **not automatically round** to one decimal digit because it "looks like 0.1".
4. The resulting `BigDecimal`'s value is **exact with respect to the `double` input**, even though it differs from the intended decimal value.
5. If the argument is `NaN` or `Infinity`, the constructor throws `NumberFormatException`: BigDecimal does not represent non-finite numbers.
6. For `-0.0`, the negative zero sign of binary64 is not preserved as a distinct signed-zero BigDecimal state.

Here "exact" means **converting the binary64 input to decimal without losing any further arithmetic information of the source value**, not **recovering a decimal fraction prior to its conversion to binary64**.

### A Simple-Looking Literal Yet Different Values

```java
BigDecimal exactBinary = new BigDecimal(0.1);
BigDecimal exactDecimal = new BigDecimal("0.1");

System.out.println(exactBinary.equals(exactDecimal));    // false
System.out.println(exactBinary.compareTo(exactDecimal)); // 1
```

`compareTo` returns positive because the exact binary64 value of `0.1` is slightly **larger** than exact 0.1. This case is not merely a difference in `scale`: **the two mathematical values genuinely differ**.

## 4. `new BigDecimal("0.1")`: Creating from Original Decimal Digits

The constructor:

```java
BigDecimal correctDecimal = new BigDecimal("0.1");
```

reads the **decimal character string**. It does not coerce `"0.1"` through `double` first. Thus, it represents **the exact fraction `1/10`**, with unscaled value 1 and scale 1.

```java
BigDecimal a = new BigDecimal("0.1");
BigDecimal b = new BigDecimal("0.2");

System.out.println(a.add(b)); // 0.3
```

This is the right approach when data is already **decimal text with exact meaning**: currencies, decimal rates, measurements provided with a fixed number of digits, values read from database DECIMAL/NUMERIC columns, or a CSV column with a decimal schema.

### Do Not Turn Strings into `double` in Between

```java
String input = "0.1";

// Avoid if required to preserve the exact entered decimal:
BigDecimal lossyPath =
        new BigDecimal(Double.parseDouble(input));

// Preserves the exact decimal as written:
BigDecimal exactPath = new BigDecimal(input);
```

The first line goes through `double` and produces an approximate binary64 value; the second line reads the decimal text directly. Once data has gone through `double`, no API can know for certain how many digits, what scale, or what unit the **original** source had.

### Source Contract Matters More Than Constructor Name

`new BigDecimal("0.1")` works when `"0.1"` is a valid decimal number string per schema. You should not take human-formatted strings like `"1,234.50"` or `"1.234,50"` and pass them straight to `BigDecimal(String)`: the constructor uses its own decimal syntax and does not automatically understand locale grouping separators.

If input is entered by users, it must be parsed according to an explicit locale/contract **without losing precision before reaching `BigDecimal`**. For locale-aware number parsing libraries, make sure they have a mode returning `BigDecimal` directly when exact decimals are required, or use a dedicated decimal parser matching the schema.

## 5. `BigDecimal.valueOf(double)`: Going Through `Double.toString`

When data **already exists as a `double`**, the following factory method is generally preferred over the constructor taking `double`:

```java
BigDecimal friendly = BigDecimal.valueOf(0.1);
System.out.println(friendly); // 0.1
```

Oracle documents that `BigDecimal.valueOf(double)` uses the **canonical string representation from `Double.toString(double)`** and constructs a `BigDecimal` from that representation.

In terms of result, one can think of it as:

```java
double source = 0.1;

BigDecimal a = BigDecimal.valueOf(source);
BigDecimal b = new BigDecimal(Double.toString(source));

System.out.println(a.equals(b)); // true
```

`Double.toString` provides a decimal representation sufficient to parse back to the original binary64 value per `double` conversion rules. For `0.1`, that representation is the short string `"0.1"`. `BigDecimal.valueOf` creates the **decimal number 0.1** from it.

### Three Ways to Create, Three Meanings

| Creation | Interpreted source | Result for `0.1` | When to choose |
| --- | --- | --- | --- |
| `new BigDecimal("0.1")` | Original decimal string | Exact `0.1` | When **reliable decimal text is available** |
| `BigDecimal.valueOf(0.1)` | `Double.toString` of input binary64 | `0.1` | When **only `double` remains** and canonical string-based decimal conversion is desired |
| `new BigDecimal(0.1)` | Exact binary64 value | `0.10000000000000000555...` | When **the exact binary64 value is intentionally needed** |

**Do not call `valueOf(double)` a "recovery machine for the original value"**: it merely picks a short, deterministic representation of the existing `double` value. If error has already accumulated in `double` calculations, that result still shows up.

### Cannot Recover Error from Intermediate Operations

```java
double binarySum = 0.1 + 0.2;

System.out.println(binarySum); // 0.30000000000000004

BigDecimal converted = BigDecimal.valueOf(binarySum);
System.out.println(converted); // 0.30000000000000004
```

Here `Double.toString(binarySum)` is `"0.30000000000000004"`, so the factory keeps that result as a decimal. It **does not fix** double addition into decimal 0.3.

To get the exact decimal result:

```java
BigDecimal decimalSum =
        new BigDecimal("0.1").add(new BigDecimal("0.2"));

System.out.println(decimalSum); // 0.3
```

**Operational rule:** if exact decimals are needed, create `BigDecimal` **right at the input boundary**, rather than waiting until a chain of `double` operations finishes to convert.

## 6. An Addition Experiment: Noise Is Preserved

With the same two literals `0.1` and `0.2`:

```java
BigDecimal sumExactOfBinary =
        new BigDecimal(0.1).add(new BigDecimal(0.2));

BigDecimal sumOfDecimalText =
        new BigDecimal("0.1").add(new BigDecimal("0.2"));

BigDecimal afterBinaryAddition =
        BigDecimal.valueOf(0.1 + 0.2);
```

Three different paths:

| Path | Result value |
| --- | --- |
| `new BigDecimal(0.1).add(new BigDecimal(0.2))` | `0.3000000000000000166533453693773481063544750213623046875` |
| `new BigDecimal("0.1").add(new BigDecimal("0.2"))` | `0.3` |
| `BigDecimal.valueOf(0.1 + 0.2)` | `0.30000000000000004` |

The differing numbers do not contradict each other:
- Path 1 converts each binary64 to BigDecimal **exactly**, then adds those two exact values in decimal.
- Path 2 starts from **exact decimals** and adds exactly.
- Path 3 **adds in double first**, gets a binary-rounded result, and then converts the result via `Double.toString`.

`BigDecimal` cannot fix a source that was already miscomputed relative to requirements. The **entire numeric data pipeline** must be designed properly from the start.

## 7. When Is the `double` Constructor Right?

Do not treat `new BigDecimal(double)` as always "wrong". It makes complete sense when the problem genuinely needs to **convert a specific binary floating-point number to its own exact decimal representation**.

Examples:
- Analyzing error of a `double` algorithm.
- Checking rounding boundaries from binary64 to decimal.
- Studying serialization/quantization and differences between shortest string and exact binary64 value.
- Creating an arithmetic reference that performs no additional rounding at **conversion** time.

```java
double binaryValue = 0.1;
BigDecimal exactRepresentation = new BigDecimal(binaryValue);
```

This is a valid engineering requirement. However, it is **not** appropriate when the requirement is "user-entered product price 0.10" or "exact decimal tax rate 0.1" where the data is available as text.

### Binary Fractions with Finite Representations

`0.5` equals `1/2`, so it is stored accurately in binary64:

```java
System.out.println(new BigDecimal(0.5)); // 0.5
```

Similarly, `0.25`, `0.125`, and many small integers also convert cleanly. The fact that a few simple tests "produce clean strings" does not prove the double constructor is safe for all decimal numbers.

## 8. Not Every Large Number Survives Passing Through `double`

Data loss does not happen only with fractional parts. `double` has a 53-bit significand, so it does not represent **every** large integer accurately.

```java
long id = 9_007_199_254_740_993L; // 2^53 + 1

BigDecimal directly = BigDecimal.valueOf(id);
BigDecimal viaDouble = BigDecimal.valueOf((double) id);

System.out.println(directly.toPlainString());
// 9007199254740993

System.out.println(viaDouble.toPlainString());
// 9007199254740992
```

Calling `BigDecimal.valueOf((double) id)` cannot recover the bit lost when casting `long -> double`. `new BigDecimal((double) id)` cannot recover it either: the constructor can represent binary64 exactly, yet binary64 **already holds a different value**.

If the source is an integer:
- `BigDecimal.valueOf(long)` creates an exact decimal integer, scale 0.
- `new BigDecimal(long)` also creates an exact integer value.
- `new BigDecimal(BigInteger)` fits integers exceeding `long`.
- **Avoid** casting through `double` just to call a constructor taking double.

Note the difference between the two overloads **`BigDecimal.valueOf(long)`** and **`BigDecimal.valueOf(double)`**. For `long`, the factory does not need a floating-point representation algorithm.

## 9. Widening `float` to `double` Does Not Recover Exact Decimals

`float` uses binary32, which has around 24 bits of significand. When passing a `float` to an API expecting `double`, Java **widens** the float value to double, but the value already quantized in binary32 does not revert to the original decimal literal.

```java
float sample = 0.1f;
double widened = sample;

System.out.println(widened); // 0.10000000149011612
System.out.println(BigDecimal.valueOf(widened));
// 0.10000000149011612
```

This is a useful example when measurements pass through `float` and are then handed to a module working with `BigDecimal`. Just because the target module uses BigDecimal, the data does **not** magically regain the decimal precision of the source.

**Strategy per requirement:**
- If you want to store the exact **float value**, `new BigDecimal((double) sample)` can be used to represent the exact existing value.
- If you want short decimal text per `Float.toString(sample)`, you can construct `new BigDecimal(Float.toString(sample))` under an explicit contract; this **differs** from the `BigDecimal.valueOf((double) sample)` path.
- If you need the original decimal of the data from before it was cast to float, you must read or preserve the **original source data**.

Do not use `Float.toString` as a fix for all errors: it is a representation policy for an existing float value, not proof of the original data.

## 10. Does Using `MathContext` Avoid Noise?

`BigDecimal` has the constructor:

```java
new BigDecimal(double value, MathContext mc)
```

It converts from `double` and rounds according to the specified precision/rounding. Example:

```java
import java.math.MathContext;
import java.math.RoundingMode;

BigDecimal rounded =
        new BigDecimal(0.1, new MathContext(4, RoundingMode.HALF_UP));
```

The result may look "clean" because it was rounded to 4 significant digits. However, that is **an intentional rounding step** from the binary64 value, **not a recovery of the original decimal**.

`MathContext` specifies **precision** (number of significant digits) and rounding mode. It is not synonymous with "always keep 2 digits after the decimal point". To specify a fixed number of fractional digits, `setScale(scale, roundingMode)` is generally more suitable.

### `setScale` Helps Normalize per Decimal Contract

```java
BigDecimal exactBinary = new BigDecimal(0.1);

BigDecimal twoDecimals =
        exactBinary.setScale(2, RoundingMode.HALF_UP);

System.out.println(twoDecimals); // 0.10
```

If business logic states "monetary amounts are defined in cents and must round HALF_UP", calling setScale at a defined boundary can make sense. **However, if you do not know whether the source data was truly 0.1 or 0.10000000000000001**, rounding cannot verify the source's intent.

`setScale(2, RoundingMode.UNNECESSARY)` requires no information loss at the target scale; with `new BigDecimal(0.1)` it normally throws `ArithmeticException` because there are non-zero remainder digits. This can serve as **a check to detect data violating a contract**, rather than a random BigDecimal bug.

### Do Not Choose Rounding Modes Arbitrarily

| Policy | Common meaning | Notes |
| --- | --- | --- |
| `RoundingMode.HALF_UP` | Round halves away from zero | Common in some business rules, not automatically right for all standards |
| `RoundingMode.HALF_EVEN` | Rounding ties to even | Useful for reducing bias when rounding repeatedly |
| `RoundingMode.DOWN` | Truncate towards 0 | Not floor for negative numbers |
| `RoundingMode.FLOOR` | Towards negative infinity | Differs from DOWN if value is negative |
| `RoundingMode.UNNECESSARY` | Forbids any rounding step | Throws exception if non-zero digits would be dropped |

Financial/tax/measurement contracts must choose the mode and **timing** of rounding. Do not automatically call `setScale(2)` with an arbitrary mode just because a value looks like money.

## 11. Comparison: Different Value and Different Scale Are Separate Issues

`BigDecimal.equals` compares both **value** and **scale**, whereas `compareTo` compares arithmetic order/value.

```java
BigDecimal a = new BigDecimal("2.00");
BigDecimal b = new BigDecimal("2.0");

System.out.println(a.equals(b));     // false
System.out.println(a.compareTo(b));  // 0
```

This is a case of **equal numeric values yet different scales**.

Conversely:

```java
BigDecimal noisy = new BigDecimal(0.1);
BigDecimal exact = new BigDecimal("0.1");

System.out.println(noisy.equals(exact));    // false
System.out.println(noisy.compareTo(exact)); // 1
```

In this case **the values genuinely differ**; it cannot be fixed by `stripTrailingZeros()` because the extra decimal digits of `noisy` are significant in the currently stored value, not all trailing zeros.

Do not use an arbitrary `double` tolerance without clear units to hide BigDecimal errors in workflows that must be exact. If "approximately equal" comparison is truly an application requirement, define an explicit decimal threshold, for example:

```java
BigDecimal difference = noisy.subtract(exact).abs();
BigDecimal tolerance = new BigDecimal("0.000000000000001");

boolean close = difference.compareTo(tolerance) <= 0;
```

This is **a tolerance policy**, not a transformation that turns `noisy` into exact 0.1. For monetary data requiring exact cents, apply scale/rounding rules to the input data and eliminate going through double from the start.

## 12. NaN, Infinity, Negative Zero, and Special Values

`double` has `NaN`, `+Infinity`, `-Infinity`, and signed zero; `BigDecimal` does not hold those non-finite states like `double`.

```java
// The following calls throw NumberFormatException:
new BigDecimal(Double.NaN);
BigDecimal.valueOf(Double.POSITIVE_INFINITY);
new BigDecimal(Double.NEGATIVE_INFINITY);
```

These are illustrative statements that **intentionally trigger exceptions**, not a code snippet to run sequentially without catching errors.

Before accepting a `double` source that might come from hardware or calculations, validate if the application requires finite numbers:

```java
static BigDecimal fromFiniteDouble(double value) {
    if (!Double.isFinite(value)) {
        throw new IllegalArgumentException("finite number required");
    }
    return BigDecimal.valueOf(value);
}
```

The illustrative method above rejects NaN/Infinity and chooses the `valueOf(double)` conversion policy, yet **does not** promise to recover source decimals.

### Negative Zero

`-0.0d` has a different bit pattern from `+0.0d`, though mathematical comparison `-0.0d == +0.0d` is true. `BigDecimal` does not model a separate signed zero, so:

```java
System.out.println(new BigDecimal(-0.0).toPlainString()); // 0
```

If the sign of zero in sensor/IEEE 754 data is part of the semantics that must be preserved, **converting to BigDecimal does not retain that information**. Design a separate data type/schema if needed.

## 13. Financial Data: Do Not Pass Through `double` for Convenience

Suppose business logic has two exact decimal amounts of 0.10 and 0.20 currency units:

```java
BigDecimal first = new BigDecimal("0.10");
BigDecimal second = new BigDecimal("0.20");

BigDecimal total = first.add(second);
System.out.println(total.toPlainString()); // 0.30
```

The exact value and scale are preserved across addition, because `add` by default picks the larger scale of the two operands.

A roundabout path to avoid:

```java
double x = 0.10;
double y = 0.20;
BigDecimal convertedTooLate = BigDecimal.valueOf(x + y);
System.out.println(convertedTooLate);
// 0.30000000000000004
```

If code is receiving numbers from CSV files, JSON, or JDBC, clarify the **data type at the boundary**:
- A `DECIMAL`/`NUMERIC` column should be read as `BigDecimal` when supported accurately by the driver/framework.
- A JSON decimal string defined by schema can be parsed directly via `new BigDecimal(text)` after validation.
- A JSON number might be deserialized by a library as `double`, `BigDecimal`, or another type; configure the parser so precision is not lost when needed.
- A monetary value with a fixed scale can be stored as an integer in the smallest unit (`long cents`) if the range/unit fits, though not every money model needs to be forced into a single approach.

**Do not process locale-formatted data like `"1.234,50"` directly with `new BigDecimal(String)`**. You need an input parser matching the locale and target type, avoiding `double` if exact decimals are desired.

## 14. Easily Confused Rounding and Representation Cases

### 14.1. `new BigDecimal(0.1).toString()` Does Not "Amplify the Error"

`toString` displays all digits needed to express the BigDecimal value exactly. It **does not perform extra math or increase error**. On the same object, `toPlainString` also only changes how exponents/decimals are displayed per contract, without changing the value.

If you see a long string after calling `toString`, the cause usually already occurred in **constructing BigDecimal from double**, not in the formatter miscalculating.

### 14.2. `BigDecimal.valueOf(double)` Still Loses Original Text Information

`BigDecimal.valueOf(1.0)` can have a different scale from `new BigDecimal("1.00")`. The factory only knows binary64 **1.0** and its canonical string; it does not know the user originally entered `"1.00"` with **two fractional digits**.

If the fractional digit count/scale carries accounting meaning, preserve the decimal text or scale as part of the contract.

### 14.3. `BigDecimal(double, MathContext)` and `setScale` Are Not the Same

The constructor with `MathContext` rounds by **total number of significant digits**. `setScale(2,...)` rounds to **two digits after the decimal point** when the target scale is 2. The two approaches can yield different results, especially with very large or very small numbers.

### 14.4. `BigDecimal` Division Does Not Automatically Generate Infinite Digits

`BigDecimal.ONE.divide(new BigDecimal("3"))` throws `ArithmeticException` because `1/3` has no finite decimal representation, unless an appropriate scale/rounding or `MathContext` is provided. This is independent of `double` noise, yet likewise shows that **BigDecimal requires you to define a rounding policy** instead of silently picking a default.

### 14.5. `BigDecimal.valueOf(double)` Does Not Turn All Operations into Decimal Arithmetic

A program like:

```java
double balance = 0.0;
balance += 0.1;
balance += 0.2;

BigDecimal after = BigDecimal.valueOf(balance);
```

still performed addition in binary64. You must convert **each source decimal value** to BigDecimal first and then add using `BigDecimal.add`. You cannot "turn on decimal mode" for a chain of `double` operations merely by changing types at the end.

## 15. Choosing Constructor/Factory by Real-World Source

| Source | Goal | Choice |
| --- | --- | --- |
| Valid decimal string `"0.10"` | Preserve exact source value and scale | `new BigDecimal("0.10")` |
| Primitive `int`/`long` | Preserve exact integer, scale 0 | `BigDecimal.valueOf(long)` or integer constructor |
| `BigInteger` | Convert very large integer | `new BigDecimal(bigInteger)` |
| Existing `double` input | Get decimal based on double's canonical string | `BigDecimal.valueOf(d)` |
| Existing `double` input | Exact binary64 value to the last digit | `new BigDecimal(d)` |
| Existing `float` input | Want decimal per `Float.toString` | `new BigDecimal(Float.toString(f))` when that is the policy |
| Decimal string with many digits currently planned to parse via `double` | Must not lose precision | Parse directly to BigDecimal, skip double step |
| JSON number in financial API | Need exact decimal on parse | Configure JSON deserializer to parse decimal tokens as BigDecimal |
| `double` operations already occurred | Cannot automatically recover original decimal | Review upstream or establish rounding policy |
| Input with locale/grouping | Need exact decimal | Parse per locale/schema to BigDecimal, do not parse via double |

### Short Decision Guide

1. **Have original decimal text?** Keep it and parse directly to BigDecimal.
2. **Have an integer primitive or BigInteger?** Convert directly, without going through double.
3. **Only have `double` left?** If you need a decimal value from the canonical string, use `BigDecimal.valueOf(d)`; if you need the **exact** binary64 value, use `new BigDecimal(d)`.
4. **Money/decimal data?** Perform calculations with BigDecimal from the beginning, with proper scale and rounding mode.
5. **Need to preserve negative zero sign, NaN, Infinity, or bit patterns?** BigDecimal cannot replace that special floating-point model.

## 16. Standalone Runnable Java 17+ Program

Create file `DecimalDoubleDemo.java`:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class DecimalDoubleDemo {
    public static void main(String[] args) {
        double d = 0.1;
        BigDecimal exact = new BigDecimal(d);
        BigDecimal text = new BigDecimal("0.1");
        BigDecimal factory = BigDecimal.valueOf(d);

        System.out.println("double text: " + Double.toString(d));
        System.out.println("new BigDecimal(0.1): " + exact.toPlainString());
        System.out.println("new BigDecimal(\"0.1\"): "
                + text.toPlainString());
        System.out.println("BigDecimal.valueOf(0.1): "
                + factory.toPlainString());
        System.out.println("exact equals text: " + exact.equals(text));
        System.out.println("factory equals text: " + factory.equals(text));
        System.out.println("exact compareTo text: "
                + exact.compareTo(text));
        System.out.println("exact scale: " + exact.scale());
        System.out.println("text scale: " + text.scale());
        System.out.println("exact unscaled: " + exact.unscaledValue());

        System.out.println("decimal sum: "
                + text.add(new BigDecimal("0.2")).toPlainString());
        System.out.println("double sum: " + Double.toString(0.1 + 0.2));
        System.out.println("factory after double sum: "
                + BigDecimal.valueOf(0.1 + 0.2).toPlainString());
        System.out.println("exact binary sum: "
                + new BigDecimal(0.1).add(new BigDecimal(0.2))
                    .toPlainString());

        System.out.println("half exactly representable: "
                + new BigDecimal(0.5).toPlainString());
        System.out.println("exact rounded to 2 decimals: "
                + exact.setScale(2, RoundingMode.HALF_UP).toPlainString());
        System.out.println("factory rounded to 2 decimals: "
                + factory.setScale(2, RoundingMode.HALF_UP).toPlainString());

        System.out.println("float promoted: "
                + BigDecimal.valueOf((double) 0.1f).toPlainString());

        long big = 9_007_199_254_740_993L;
        System.out.println("long exact: "
                + BigDecimal.valueOf(big).toPlainString());
        System.out.println("long through double: "
                + BigDecimal.valueOf((double) big).toPlainString());

        try {
            new BigDecimal(Double.NaN);
        } catch (NumberFormatException ex) {
            System.out.println("NaN rejected: true");
        }
        try {
            BigDecimal.valueOf(Double.POSITIVE_INFINITY);
        } catch (NumberFormatException ex) {
            System.out.println("Infinity rejected: true");
        }

        System.out.println("negative zero from double: "
                + new BigDecimal(-0.0).toPlainString());
        System.out.println("2.00 equals 2.0: "
                + new BigDecimal("2.00")
                    .equals(new BigDecimal("2.0")));
        System.out.println("2.00 compareTo 2.0: "
                + new BigDecimal("2.00")
                    .compareTo(new BigDecimal("2.0")));
    }
}
```

Compile and run with JDK 17 or higher:

```bash
javac --release 17 DecimalDoubleDemo.java
java DecimalDoubleDemo
```

Verified stdout:

```text
double text: 0.1
new BigDecimal(0.1): 0.1000000000000000055511151231257827021181583404541015625
new BigDecimal("0.1"): 0.1
BigDecimal.valueOf(0.1): 0.1
exact equals text: false
factory equals text: true
exact compareTo text: 1
exact scale: 55
text scale: 1
exact unscaled: 1000000000000000055511151231257827021181583404541015625
decimal sum: 0.3
double sum: 0.30000000000000004
factory after double sum: 0.30000000000000004
exact binary sum: 0.3000000000000000166533453693773481063544750213623046875
half exactly representable: 0.5
exact rounded to 2 decimals: 0.10
factory rounded to 2 decimals: 0.10
float promoted: 0.10000000149011612
long exact: 9007199254740993
long through double: 9007199254740992
NaN rejected: true
Infinity rejected: true
negative zero from double: 0
2.00 equals 2.0: false
2.00 compareTo 2.0: 0
```

This example contrasts the **three initialization mechanisms**, values and scales, differences in addition, `float` effects, large integer loss via `double`, NaN/Infinity, and scale-based equality. Most importantly, the very long strings **are explained by the binary64 input**, not "instability" in BigDecimal addition.

## 17. Recommended Test Cases

| Test | Input / action | Expectation |
| --- | --- | --- |
| Double constructor | `new BigDecimal(0.1)` | Exact decimal value of binary64, long digits |
| Text constructor | `new BigDecimal("0.1")` | Exact decimal 0.1, scale 1 |
| Double factory | `BigDecimal.valueOf(0.1)` | `0.1`, matching `Double.toString` |
| Factory after double addition | `BigDecimal.valueOf(0.1+0.2)` | `0.30000000000000004` |
| Exact decimal addition | `new BigDecimal("0.1").add(new BigDecimal("0.2"))` | `0.3` |
| Adding two exact binary64s | `new BigDecimal(0.1).add(new BigDecimal(0.2))` | Not equal to exact decimal 0.3 |
| Finitely representable binary fraction | `new BigDecimal(0.5)` | `0.5` |
| Widened float | `BigDecimal.valueOf((double)0.1f)` | `0.10000000149011612` |
| Integer via double | `2^53+1` cast long → double → BigDecimal | Off by 1 unit |
| Created from long | `BigDecimal.valueOf(9007199254740993L)` | Exact |
| NaN | `new BigDecimal(Double.NaN)` | `NumberFormatException` |
| Infinity | `BigDecimal.valueOf(+Infinity)` | `NumberFormatException` |
| Signed zero | `new BigDecimal(-0.0)` | BigDecimal value equals 0, does not preserve signed-zero |
| Scale vs numerical equality | `"2.00"` and `"2.0"` | `equals=false`, `compareTo=0` |
| Rounding 2 decimals | `exactBinary.setScale(2, HALF_UP)` | `0.10`; rounding is policy, does not recover source text |

Beyond arithmetic tests, test the **end-to-end data pipeline** from CSV/JSON/JDBC through the service layer to DB writes or file exports: does any part implicitly coerce decimals to `double`? The bug may lie in framework configuration, type mapping, or serializers rather than directly in a constructor inside business code.

## 18. Common Mistakes and Fixes

| Mistake | Consequence | Appropriate approach |
| --- | --- | --- |
| Using `new BigDecimal(0.1)` expecting exact decimal 0.1 | Receives exact binary64, producing many decimal digits | Use `new BigDecimal("0.1")` when decimal text is available |
| Calling the long string a "BigDecimal rounding bug" | Misdiagnoses the root cause | Check whether data passed through `double` before creating BigDecimal |
| Believing `BigDecimal.valueOf(double)` always fixes errors | Earlier double addition still retains error | Create and compute with BigDecimal from the source |
| Using `String.valueOf(double)` to recover all originally entered digits | Short string only preserves double round-trip | Keep decimal text from the start if needed |
| Converting large `long` to `double` then calling `valueOf` | Loses integer precision > 2^53 | `BigDecimal.valueOf(long)` or `BigInteger` |
| Using `new BigDecimal(0.1f)` thinking it is decimal 0.1 | `float` already approximated and widened to double | Use decimal source, or Float.toString per policy |
| Using `setScale(2, HALF_UP)` everywhere to hide noise | Can drop valid value and violate rounding rules | Specify unit/scale/mode at boundaries |
| Thinking `MathContext(2)` means 2 fractional digits | It means 2 **significant** digits | Distinguish `precision` and `scale` |
| Using `equals` as a check for equal mathematical value | `equals` checks scale too | `compareTo==0` when scale is not needed |
| Believing `stripTrailingZeros` removes noise | Extra digits are not necessarily zero | Handle source properly, do not blindly sanitize |
| Passing NaN/Infinity into BigDecimal | `NumberFormatException` | Check `Double.isFinite`; handle separately in schema |
| Believing BigDecimal keeps `-0.0` sign | No signed-zero like double | Keep bit/metadata in a separate model if needed |
| Parsing decimal numbers via `Double.parseDouble` before `BigDecimal` | Loses precision in intermediate step | `new BigDecimal(text)` directly |
| Assuming BigDecimal can always divide with a finite result | 1/3 is an infinite decimal | Use `divide` with scale/rounding when appropriate |
| Rounding at multiple intermediate steps without policy | Wrong totals/taxes/measurements | Define rounding points and preserve exactness beforehand |
| Transmitting money as JSON number and letting clients parse binary64 arbitrarily | Loses precision/scale in integration | Design exact decimal schema and parser |

## 19. Self-Check Questions

1. Why does the literal `0.1` in a `double` fail to hold the mathematical fraction `1/10` accurately?
2. What value does `new BigDecimal(0.1)` hold? Why can a long decimal string be an **exact conversion**?
3. `new BigDecimal("0.1")` and `BigDecimal.valueOf(0.1)` appear to give the same result. Do they have the same source of information?
4. Why does `BigDecimal.valueOf(0.1 + 0.2)` not produce decimal 0.3?
5. How do the two paths `new BigDecimal(0.1).add(new BigDecimal(0.2))` and `BigDecimal.valueOf(0.1+0.2)` differ in rounding/conversion order?
6. Which fractions like `0.5`, `0.25`, `0.125` are finitely represented by binary64? What is the denominator criterion?
7. Does `BigDecimal.valueOf(0.1f)` recover the original decimal text 0.1? Why does widening float to double not do so?
8. Why can `2^53+1` lose precision when converting from `long` to `double`?
9. If receiving the monetary string `"1234.50"`, which constructor do you choose to preserve both value and scale? What happens if parsed through double?
10. How do `MathContext` and `setScale` differ regarding precision and digits after the decimal point?
11. What does `new BigDecimal(0.1).setScale(2, HALF_UP)` return? Has it definitively recovered the decimal source value?
12. How do `BigDecimal.equals` and `compareTo` differ when comparing `2.00` with `2.0`?
13. Does `new BigDecimal(Double.NaN)` create an object? Why or why not?
14. Does `BigDecimal` preserve the sign bit of `-0.0`? If an application needs that, what is the solution?
15. At which boundaries will you inspect to ensure the whole system computes exact decimals, from ingestion to database and API?

## 20. Official References

- [Java SE 17 — `BigDecimal(double)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html#%3Cinit%3E(double)): defines converting a binary64 value to exact decimal, e.g., `0.1`, and recommends against using this constructor when wanting the decimal the user intended.
- [Java SE 17 — `BigDecimal.valueOf(double)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html#valueOf(double)): converts via the canonical representation of `Double.toString(double)`.
- [Java SE 17 — `BigDecimal(String)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html#%3Cinit%3E(java.lang.String)): reads decimal string directly, without going through double.
- [Java SE 17 — `BigDecimal`: precision, scale, MathContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): unscaled value/scale model, operations, and rounding.
- [Java SE 17 — `Double`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html): `Double.toString`, `parseDouble`, binary64, NaN, and Infinity.
- [Java Language Specification `4.2.3](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2.3): range, representation, and behavior of Java floating-point numbers.

**Takeaway:** `new BigDecimal(double)` is an **exact conversion of the binary64 value**, so long decimal strings can appear as when using `0.1`. `new BigDecimal("0.1")` keeps the exact decimal from source characters; `BigDecimal.valueOf(0.1)` creates a decimal from the canonical `Double.toString` string of an existing double. There is no way to reliably recover decimal data **already lost** in double calculation steps. For systems requiring exact decimals, the best choice is to **keep decimal data and process with BigDecimal from the input boundary**, then round according to a clearly defined policy.