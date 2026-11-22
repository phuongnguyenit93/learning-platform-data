# BigDecimal.toEngineeringString(): Exponents as Multiples of 3

## 1. What Is Engineering Notation?

When a number is very large or very small, it is commonly written in *scientific notation*:

~~~text
12 300 000 = 1.23 × 10^7
0.000000123 = 1.23 × 10^-7
~~~

In **engineering notation**, the exponent of 10 is chosen to be an **integer multiple of 3**:

~~~text
12 300 000 = 12.3 × 10^6
0.000000123 = 123 × 10^-9
~~~

This is helpful when reading numbers in groups of three orders of magnitude: thousand (`10^3`), million (`10^6`), billion (`10^9`), milli (`10^-3`), micro (`10^-6`), nano (`10^-9`). Java supports converting a `BigDecimal` object into a string in this format using:

~~~java
String text = number.toEngineeringString();
~~~

`toEngineeringString()` returns a `String` representing the **exact same mathematical value**. The method does not round, does not limit precision, does not change units of measurement, and does not modify the original `BigDecimal` object.

Example:

~~~java
BigDecimal x = new BigDecimal("1E+4");
System.out.println(x.toString());            // 1E+4
System.out.println(x.toEngineeringString()); // 10E+3
System.out.println(x.toPlainString());       // 10000
~~~

All three strings represent the value 10,000. The difference is where the decimal point is placed and what exponent is used.

## 2. The "Exponent Is a Multiple of 3" Rule

In a string like `ME+n`, the `E` indicates a decimal power of 10:

~~~text
M E n = M × 10^n

1E+4 = 1 × 10^4 = 10000
10E+3 = 10 × 10^3 = 10000
100E-9 = 100 × 10^-9 = 0.0000001
~~~

For a **non-zero** number written with `E`:

- Normalized scientific notation normally places one non-zero digit before the decimal point, corresponding to `1 ≤ |M| < 10`.
- Engineering notation places one to three digits before the decimal point, corresponding to `1 ≤ |M| < 1000`; the exponent `n` is divisible by 3.
- The sign of the number is kept on the significand: `-10E+3` equals `-10000`.
- Exponents can be negative: `-3`, `-6`, `-9` are also multiples of 3.

| Value | Scientific Form | Engineering Form | Why |
|---|---|---|---|
| 10,000 | `1E+4` | `10E+3` | Decrease exponent 4 to 3 and multiply significand by 10 |
| 100,000 | `1E+5` | `100E+3` | Decrease exponent 5 to 3 and multiply significand by 100 |
| 1,000,000 | `1E+6` | `1E+6` | Exponent 6 is already divisible by 3 |
| 0.0000001 | `1E-7` | `100E-9` | Exponent -9 is divisible by 3 |
| 0.00000001 | `1E-8` | `10E-9` | Exponent -9 is divisible by 3 |
| 0.000000001 | `1E-9` | `1E-9` | Exponent -9 already fits |

Shifting the decimal point in the significand `r` digits to the right requires decreasing the exponent by `r` to **preserve the value**:

~~~text
M × 10^e = (M × 10^r) × 10^(e-r)

1.23 × 10^-7 = 123 × 10^-9
1.2345 × 10^8 = 123.45 × 10^6
~~~

The conversion requires no `double` floating-point arithmetic whatsoever.

**Important:** "Exponent is a multiple of 3" applies **only when Java decides to output a string with `E` notation**. `toEngineeringString()` does not force `E` to be printed for every object.

## 3. Comparing toString(), toEngineeringString(), and toPlainString()

These are three different string output methods on `BigDecimal`:

| Method | Representation | Can Contain `E`? | Purpose |
|---|---|---|---|
| `toString()` | Canonical representation, may be scientific or plain form | Yes | Convert number to canonical string, preserving the value–scale pair when parsed back |
| `toEngineeringString()` | If `E` is used, exponent is a multiple of 3 | Yes | Present in groups of three decimal orders of magnitude |
| `toPlainString()` | Standard decimal form, no exponent printed | No | Ordinary number string without `E` |

Comparing actual return values:

| Constructor | `toString()` | `toEngineeringString()` | `toPlainString()` |
|---|---|---|---|
| `new BigDecimal("1E+4")` | `1E+4` | `10E+3` | `10000` |
| `new BigDecimal("1E+5")` | `1E+5` | `100E+3` | `100000` |
| `new BigDecimal("1E+6")` | `1E+6` | `1E+6` | `1000000` |
| `new BigDecimal("1E-7")` | `1E-7` | `100E-9` | `0.0000001` |
| `new BigDecimal("1E-8")` | `1E-8` | `10E-9` | `0.00000001` |
| `new BigDecimal("1E-9")` | `1E-9` | `1E-9` | `0.000000001` |
| `new BigDecimal("0.000000123")` | `1.23E-7` | `123E-9` | `0.000000123` |
| `new BigDecimal("12345.00")` | `12345.00` | `12345.00` | `12345.00` |
| `new BigDecimal("1000")` | `1000` | `1000` | `1000` |
| `new BigDecimal("0E+7")` | `0E+7` | `0.00E+9` | `0` |

For `new BigDecimal("1000")`, all three methods print `1000`. The engineering method **does not automatically force 1000 into `1E+3`**. Similarly, `new BigDecimal("123456789").toEngineeringString()` still returns `"123456789"` even though the value is fairly large.

This is an easy mistake to make when writing programs that require "every number must be printed with an engineering exponent." If the contract requires **always having `E`**, you must use a custom-configured formatter, including precision, rounding, and locale rules. `toEngineeringString()` alone does not guarantee that format.

## 4. Why Does Java Sometimes Print Plain Decimal Form?

A `BigDecimal` consists of two components: an integer unscaled value (`unscaledValue`) and a `scale`:

~~~text
value = unscaledValue × 10^(-scale)
~~~

`scale()` can be positive, zero, or negative. `precision()` is the number of digits in the unscaled integer, excluding the sign. Examples:

| Object | `precision()` | `scale()` | Value |
|---|---:|---:|---|
| `new BigDecimal("123.4500")` | 7 | 4 | 123.4500 |
| `new BigDecimal("1000")` | 4 | 0 | 1000 |
| `new BigDecimal("1E+3")` | 1 | -3 | 1000 |
| `new BigDecimal("0.0000001")` | 1 | 7 | 0.0000001 |

For a non-zero number, the *adjusted exponent* is:

~~~text
adjustedExponent = precision() - scale() - 1
~~~

For both `toString()` and `toEngineeringString()`, if `scale >= 0` and `adjustedExponent >= -6`, Java uses plain decimal form. When that condition is not met, the string typically uses `E` notation; `toEngineeringString()` adjusts it so the exponent of `E` is a multiple of 3. The specific rules for zero have representation exceptions because zero has no unique normalized significand.

Boundary example:

~~~java
BigDecimal a = new BigDecimal("0.000001");  // precision=1, scale=6
BigDecimal b = new BigDecimal("0.0000001"); // precision=1, scale=7

System.out.println(a.toEngineeringString()); // 0.000001
System.out.println(b.toEngineeringString()); // 100E-9
~~~

The first number has an adjusted exponent of `-6`, so it still prints normally; the second has an adjusted exponent of `-7`, so it uses exponential notation. Therefore, you cannot simply assume that "any number smaller than 1 has `E`."

## 5. Standalone Runnable Java 17+ Program

Create a file named `EngineeringStringDemo.java` with the following contents:

~~~java
import java.math.BigDecimal;

public class EngineeringStringDemo {
    public static void main(String[] args) {
        String[] inputs = {
            "1E+4", "1E+5", "1E+6",
            "1E-7", "1E-8", "1E-9",
            "0.000000123", "12345.00", "1000", "0E+7"
        };

        for (String input : inputs) {
            BigDecimal number = new BigDecimal(input);
            System.out.println(
                    input
                    + " | sci=" + number.toString()
                    + " | eng=" + number.toEngineeringString()
                    + " | plain=" + number.toPlainString());
        }

        BigDecimal original = new BigDecimal("1E+4");
        BigDecimal fromEngineering =
                new BigDecimal(original.toEngineeringString());
        BigDecimal fromCanonical =
                new BigDecimal(original.toString());

        System.out.println("original scale=" + original.scale());
        System.out.println("engineering scale=" + fromEngineering.scale());
        System.out.println("same numeric value="
                + (original.compareTo(fromEngineering) == 0));
        System.out.println("same representation="
                + original.equals(fromEngineering));
        System.out.println("canonical preserves representation="
                + original.equals(fromCanonical));
    }
}
~~~

Compile and run using JDK 17 or newer:

~~~bash
javac EngineeringStringDemo.java
java EngineeringStringDemo
~~~

Expected output:

~~~text
1E+4 | sci=1E+4 | eng=10E+3 | plain=10000
1E+5 | sci=1E+5 | eng=100E+3 | plain=100000
1E+6 | sci=1E+6 | eng=1E+6 | plain=1000000
1E-7 | sci=1E-7 | eng=100E-9 | plain=0.0000001
1E-8 | sci=1E-8 | eng=10E-9 | plain=0.00000001
1E-9 | sci=1E-9 | eng=1E-9 | plain=0.000000001
0.000000123 | sci=1.23E-7 | eng=123E-9 | plain=0.000000123
12345.00 | sci=12345.00 | eng=12345.00 | plain=12345.00
1000 | sci=1000 | eng=1000 | plain=1000
0E+7 | sci=0E+7 | eng=0.00E+9 | plain=0
original scale=-4
engineering scale=-3
same numeric value=true
same representation=false
canonical preserves representation=true
~~~

The label `sci` in the example only helps contrast with `toString()`; this method does not always have to return scientific notation. The `1000` and `12345.00` lines show that the result can be a plain decimal number.

The final lines verify an important property when **parsing an engineering-notation string back** into a `BigDecimal`: the same numeric value does not necessarily have the same `scale`.

## 6. Parsing Engineering Strings: Preserves Value, May Change Scale

The `new BigDecimal(String)` constructor accepts `E` notation, for example:

~~~java
BigDecimal parsed = new BigDecimal("10E+3");
System.out.println(parsed.toPlainString()); // 10000
~~~

However, if you subsequently parse the string returned by `toEngineeringString()`, the before and after objects **may have different scales**:

~~~java
BigDecimal before = new BigDecimal("1E+4");  // 1 × 10^4
String text = before.toEngineeringString();  // "10E+3"
BigDecimal after = new BigDecimal(text);      // 10 × 10^3

System.out.println(before.scale());          // -4
System.out.println(after.scale());           // -3
System.out.println(before.compareTo(after)); // 0
System.out.println(before.equals(after));    // false
~~~

Why? `BigDecimal` computes its value using the formula `unscaledValue × 10^(-scale)`:

| Object | Unscaled value | Scale | Value |
|---|---:|---:|---:|
| `before`, created from `"1E+4"` | 1 | -4 | 10000 |
| `after`, created from `"10E+3"` | 10 | -3 | 10000 |

`compareTo() == 0` indicates equal mathematical values. `equals()` requires equal values **and equal scales**; hence it returns `false` here. This is `BigDecimal`'s behavior, not a bug in `toEngineeringString()`.

| String Output and Reconstructed via `new BigDecimal(text)` | Preserves Mathematical Value? | Always Preserves Scale? |
|---|---|---|
| `x.toString()` | Yes | **Yes**: canonical representation of `BigDecimal` |
| `x.toEngineeringString()` | Yes | **Not necessarily** |
| `x.toPlainString()` | Yes | **Not necessarily**, especially when scale is negative |

With `toPlainString()`, for instance, `new BigDecimal("1E+4")` outputs `"10000"`. Parsing it back into `new BigDecimal("10000")` gives scale 0, different from the original scale -4.

**Practical rule:** if you only need the numeric value, you can compare using `compareTo(other) == 0`. If serialization/deserialization must preserve the representation as well (`scale`, which is part of `equals()` semantics), use `toString()` and `new BigDecimal(String)`. Do not use `toEngineeringString()` as a scale-exact round-trip format in data contracts.

## 7. Zero Is a Special Case

Non-zero numbers can normalize their significand into the range from 1 to less than 1000, but zero cannot: any expression `0 × 10^n` is still 0. Therefore, Java also uses zeros after the decimal point to express scale.

~~~java
BigDecimal zero = new BigDecimal("0E+7");
System.out.println(zero.toString());            // 0E+7
System.out.println(zero.toEngineeringString()); // 0.00E+9
System.out.println(zero.toPlainString());       // 0
~~~

`0.00E+9` still equals 0; the exponent 9 is a multiple of 3. This exponent cannot be deduced from the "magnitude" of zero; it depends on the object's representation. Parsing `"0.00E+9"` can even preserve the `-7` scale of `"0E+7"`, because the two decimal zeros are part of the significand.

Another example:

~~~java
System.out.println(new BigDecimal("0E-7").toEngineeringString());
// 0.0E-6
~~~

For zero, do not mechanically apply the `1 ≤ |M| < 1000` significand rule. When building a custom engineering-notation converter, handle zero separately and do not draw conclusions about precision or scale solely from a magnitude of zero.

## 8. Trailing Zeros and stripTrailingZeros()

The following `BigDecimal` objects all have the value 1000 but different representations:

~~~java
BigDecimal first = new BigDecimal("1E+3");
BigDecimal second = new BigDecimal("1000");
BigDecimal third = new BigDecimal("1000.00");

System.out.println(first.toEngineeringString());  // 1E+3
System.out.println(second.toEngineeringString()); // 1000
System.out.println(third.toEngineeringString());  // 1000.00
~~~

`first` has scale -3, `second` has scale 0, and `third` has scale 2. Trailing zeros in the input string can affect precision and scale, even though the mathematical value does not change.

`stripTrailingZeros()` returns a new `BigDecimal`, removing unnecessary trailing zeros from the unscaled value; in this case, the scale changes:

~~~java
BigDecimal count = new BigDecimal("1000");
BigDecimal stripped = count.stripTrailingZeros();

System.out.println(count.toEngineeringString());    // 1000
System.out.println(stripped.toEngineeringString()); // 1E+3
System.out.println(stripped.scale());               // -3
~~~

Thus `stripTrailingZeros()` **does not just change display**, it also alters the representation of the resulting object. If used before serialization, you may inadvertently change the outcome of `equals()` or scale-dependent operations.

Do not mechanically use `stripTrailingZeros()` to force every number into `E` form: for numbers without trailing zeros like `123456789`, the method will not produce an exponent.

## 9. Engineering Notation Does Not Perform Rounding

`toEngineeringString()` does not round. If a number has many significant digits, the engineering string still represents the full value:

~~~java
BigDecimal x = new BigDecimal("1.23456789012345E+7");
System.out.println(x.toEngineeringString());
// 12.3456789012345E+6
~~~

If the problem requires limiting the number of significant digits, you must round separately before converting to a string:

~~~java
import java.math.MathContext;
import java.math.RoundingMode;

BigDecimal x = new BigDecimal("1.23456789E+7");
BigDecimal rounded = x.round(new MathContext(4, RoundingMode.HALF_UP));

System.out.println(rounded.toEngineeringString()); // 12.35E+6
~~~

`round(MathContext)` specifies precision and rounding mode; `toEngineeringString()` only specifies the representation format. Similarly, `setScale(2, RoundingMode.HALF_UP)` rounds to two decimal places, not to make the exponent a multiple of 3.

Another method easily confused with this is `scaleByPowerOfTen(n)`:

~~~java
BigDecimal a = new BigDecimal("123");
BigDecimal b = a.scaleByPowerOfTen(3); // value 123000
~~~

`scaleByPowerOfTen(3)` **actually changes the value** by multiplying by `10^3`. It is not a tool for rewriting the number 123 in engineering notation while keeping the same value.

## 10. Application Example and API Selection

Suppose a sensor records electric current in amperes:

~~~java
BigDecimal currentAmpere = new BigDecimal("0.000000123");
String engineering = currentAmpere.toEngineeringString();

System.out.println(engineering + " A"); // 123E-9 A
~~~

`123E-9 A` and `0.000000123 A` have the same value. If you want the output to be `123 nA`, the application must choose the **unit prefix** itself and handle conversion according to the engineering contract; `toEngineeringString()` does not add `n`, `μ`, `m`, `k`, or `M`.

Good use cases include electrical/electronics reports, presenting physical quantities spanning many orders of magnitude, measurement data, and engineering tables customarily read in multiples of 1000.

| Requirement | Method / Approach |
|---|---|
| Canonical string that can be parsed back and preserves scale | `toString()` |
| String without `E` notation | `toPlainString()` |
| When printing exponents, exponent should be a multiple of 3 | `toEngineeringString()` |
| Always require engineering exponent, even for ordinary integers | Custom formatter with explicit rules |
| Limit number of significant digits | `round(MathContext)` before outputting string |
| Set fixed number of decimal places | `setScale(scale, mode)` per business rules |
| Convert units, add SI prefixes | Separate unit-handling logic after determining value and SI order |

In APIs, JSON, CSV, and storage, distinguish three things: (1) whether the client accepts exponential strings, (2) whether `scale` must be preserved, and (3) whether user locale or units must be followed. `toEngineeringString()` uses Java numeric syntax (period and `E`), which does not mean every external protocol accepts this format.

## 11. Common Mistakes

| Misconception | Reality | How to Avoid |
|---|---|---|
| "Calling engineering always produces E" | `new BigDecimal("1000")` still returns `1000` | Check whether exponential output is mandatory |
| "Using engineering rounds the number" | The method only creates a string | Round separately using context or scale |
| "`10E+3` is 10 thousand, different from `1E+4`" | Same value 10000 | Check significand × `10^exponent` |
| "Negative exponents aren't multiples of three" | `-3`, `-6`, `-9` are multiples of three | Account for negative exponents too |
| "Parsing an engineering string back always equals the original" | Can change `scale` | Use `toString()` if representation round-trip is needed |
| "Zero follows the same significand rule as non-zero numbers" | `0.00E+9` is a valid result | Handle zero separately |
| "`stripTrailingZeros` only changes the string" | Returns an object whose scale may change | Check impact on equals / formatting |
| "Engineering includes kilo/micro units" | Only has the exponent, no unit | Write separate unit conversion logic |
| "Parsing `toPlainString` back always preserves scale" | Negative scales are lost | Choose `toString` when scale preservation is required |
| "Seeing E+6 means BigDecimal used double" | `E` string is decimal notation, not implying `double` type | Separate string representation from data type |

## 12. Self-Check Exercises

**Exercise 1.** What is `new BigDecimal("1E+8").toEngineeringString()`?

**Answer:** `100E+6`, because `1 × 10^8 = 100 × 10^6`. The exponent 6 is divisible by 3.

**Exercise 2.** Why is `new BigDecimal("1E-7").toEngineeringString()` equal to `100E-9` instead of `1E-6`?

**Answer:** `1E-6` is ten times larger than `1E-7`. You must increase the significand to `100` and decrease the exponent to `-9` to keep the value unchanged.

**Exercise 3.** Why do two numbers both equal to 1000 produce `1000` for `new BigDecimal("1000").toEngineeringString()` and `1E+3` for `new BigDecimal("1E+3").toEngineeringString()`?

**Answer:** The `BigDecimal` objects hold different scales (0 vs. -3). The rule for printing exponents inspects the representation, not just the magnitude of the value.

**Exercise 4.** Does parsing `"10E+3"` and comparing it with `new BigDecimal("1E+4")` using `equals()` return `true`?

**Answer:** No. Both numbers have the same value, but scales -3 and -4. `compareTo() == 0` returns `true`.

**Exercise 5.** When you need to always print engineering notation with `E` for the number `123456789`, is calling `toEngineeringString()` alone sufficient?

**Answer:** No. For an object with scale 0 like that, Java picks plain form. You need a dedicated formatting tool that explicitly defines precision/rounding and output layout.

**Exercise 6.** Describe the result of `new BigDecimal("0E+7").toEngineeringString()`.

**Answer:** `0.00E+9`. The value is still 0 and exponent 9 is a multiple of 3; the zeros in the significand help express the scale of zero.

---

**Takeaway:** `toEngineeringString()` is a **string conversion**; when the string uses `E` notation, the exponent will be a multiple of 3. The numeric value does not change, but parsing the string back can produce a `BigDecimal` with a different scale. Choose `toString()` for scale-preserving round-trips, `toPlainString()` to avoid printing `E`, and `toEngineeringString()` to present values in engineering notation when appropriate.
