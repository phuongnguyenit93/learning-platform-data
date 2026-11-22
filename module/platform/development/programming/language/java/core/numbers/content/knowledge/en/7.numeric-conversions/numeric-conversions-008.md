# Converting via Number.intValue(), longValue(), and doubleValue() in Java

## 1. Why does Java have these conversion methods?

In Java, `java.lang.Number` is the common **abstract class** for classes representing numeric values, such as `Byte`, `Short`, `Integer`, `Long`, `Float`, `Double`, `BigInteger`, and `BigDecimal`. `Number` allows programs to work with many kinds of numbers through a single reference type:

~~~java
Number quantity = Integer.valueOf(42);
int count = quantity.intValue();
long total = quantity.longValue();
double measured = quantity.doubleValue();
~~~

The snippet above is illustrative code inside a method. At runtime, `quantity` points to an `Integer` object, so the calls execute according to `Integer`'s implementation. If the object is replaced with `Double` or `BigDecimal`, **the return types remain fixed**, yet the specific conversion rules can lead to a different value, precision loss, or loss of high bits.

Three core APIs:

| `Number` method | Return type | Meaning |
| --- | --- | --- |
| `intValue()` | Signed 32-bit `int` | Get value as a 32-bit integer |
| `longValue()` | Signed 64-bit `long` | Get value as a 64-bit integer |
| `doubleValue()` | IEEE 754 binary64 `double` | Get value as a 64-bit floating-point number |

These calls **do not create `Integer`, `Long`, or `Double` objects**: they return **primitive** values. If assigned to a corresponding wrapper variable, Java may auto-box the result, such as `Integer boxed = quantity.intValue();`.

## 2. The Number class: a common type, where the actual object decides behavior

`Number` declares four abstract methods: `intValue()`, `longValue()`, `floatValue()`, and `doubleValue()`. Additionally, `byteValue()` and `shortValue()` are concrete default methods that convert via `intValue()` and then cast to `byte` or `short`. Standard numeric classes implement conversion behavior suited to how each class stores data.

~~~java
Number first = Long.valueOf(20L);
Number second = Double.valueOf(20.9);
Number third = new java.math.BigDecimal("20.9");

System.out.println(first.intValue());  // 20
System.out.println(second.intValue()); // 20
System.out.println(third.intValue());  // 20
~~~

Although all three results look the same, the reasons are not identical: `Long` converts an integer to `int`; `Double` converts a floating-point number to an integer under Java's floating-point rules; `BigDecimal` drops the fractional part and takes the integer part representable in 32 bits. For out-of-bounds values, the differences become much more pronounced.

`Number` is a **class**, not an interface. Because a `Number` reference can point to many subclasses, do not assume every `Number` is exact, finite, or within the `int` range. Code using `Number` must also handle the possibility of `null`.

## 3. intValue(): converting to 32-bit int

`intValue()` returns an `int` in the range from −2,147,483,648 to 2,147,483,647.

### 3.1. When the source is Integer, Short, or Byte

When the source is already `Integer`, the value is preserved. `Byte` and `Short` have smaller ranges than `int`, so every value is represented exactly when widened to `int`.

~~~java
Number a = Byte.valueOf((byte) -7);
Number b = Short.valueOf((short) 32000);
Number c = Integer.valueOf(100000);

System.out.println(a.intValue()); // -7
System.out.println(b.intValue()); // 32000
System.out.println(c.intValue()); // 100000
~~~

### 3.2. When the source is Long: keeping the low 32 bits

`Long.intValue()` is equivalent to the narrowing conversion `(int) longValue`: Java keeps the **low 32 bits** and interprets them as a signed `int`. This is not an overflow-checked conversion; the value can change drastically.

~~~java
Number n = Long.valueOf(3_000_000_000L);

System.out.println(n.intValue());  // -1294967296
System.out.println(n.longValue()); // 3000000000
~~~

Because 3,000,000,000 is greater than `Integer.MAX_VALUE`, the low 32 bits have their sign bit set to 1; that same bit pattern is represented as `-1294967296` when read as an `int`.

If you must preserve values within the `int` range, for a specific `long` source use `Math.toIntExact(long)`; this API throws `ArithmeticException` when out of range:

~~~java
long raw = 3_000_000_000L;
try {
    int safe = Math.toIntExact(raw);
    System.out.println(safe);
} catch (ArithmeticException ex) {
    System.out.println("Exceeds int range");
}
~~~

### 3.3. When the source is Double or Float: dropping fractions, with rules for special values

For a `Double`/`Float` source, `intValue()` follows Java's floating-point-to-`int` cast rules:

- Fractional parts are **truncated toward zero**, not rounded to nearest: `12.9 → 12`; `-12.9 → -12`.
- `NaN → 0`.
- Overly large positive numbers or `+Infinity → Integer.MAX_VALUE`.
- Overly small negative numbers or `-Infinity → Integer.MIN_VALUE`.

~~~java
System.out.println(Double.valueOf(12.9).intValue());                // 12
System.out.println(Double.valueOf(-12.9).intValue());               // -12
System.out.println(Double.valueOf(Double.NaN).intValue());         // 0
System.out.println(Double.valueOf(Double.POSITIVE_INFINITY).intValue()); // 2147483647
System.out.println(Double.valueOf(Double.NEGATIVE_INFINITY).intValue()); // -2147483648
~~~

This rule is often called **saturation** in out-of-range cases for floating-point-to-integral conversions. Do not apply it to `Long.intValue()` or `BigInteger.intValue()`; those two types take the low bits and wrap around rather than clamping at `Integer.MAX_VALUE`.

### 3.4. When the source is BigInteger or BigDecimal

`BigInteger.intValue()` keeps only the low 32 bits of the large integer. `BigDecimal.intValue()` first discards the fractional part, and then the final result may keep only the low 32 bits. Therefore, **`intValue()` cannot be treated as a range-checked or fraction-checked conversion**.

~~~java
Number huge = new java.math.BigInteger("4294967303"); // 2^32 + 7
Number decimal = new java.math.BigDecimal("-12.99");

System.out.println(huge.intValue());    // 7
System.out.println(decimal.intValue()); // -12
~~~

If the source is `BigInteger` or `BigDecimal` and an exact integer value is required, use `intValueExact()` on that class itself. `BigDecimal.intValueExact()` also fails if the fractional part is nonzero.

## 4. longValue(): converting to 64-bit long

`longValue()` returns a `long` in the range from −9,223,372,036,854,775,808 to 9,223,372,036,854,775,807.

- From `Byte`, `Short`, `Integer`, or `Long`: the integer value is preserved because all fit inside `long`.
- From `Double`/`Float`: drops the fractional part toward 0, `NaN → 0L`, positive overflow/`+Infinity → Long.MAX_VALUE`, negative overflow/`-Infinity → Long.MIN_VALUE`.
- From `BigInteger`: keeps only the **low 64 bits**, even when the original number exceeds `Long.MAX_VALUE`.
- From `BigDecimal`: drops the fractional part and can then lose high bits when outside the `long` range.

~~~java
Number fromInt = Integer.valueOf(-150);
Number fromDouble = Double.valueOf(98.75);
Number fromHuge = new java.math.BigInteger("18446744073709551617"); // 2^64 + 1

System.out.println(fromInt.longValue());    // -150
System.out.println(fromDouble.longValue()); // 98
System.out.println(fromHuge.longValue());   // 1
~~~

In the last example, `18446744073709551617 = 2^64 + 1`. Keeping only the low 64 bits yields a bit pattern equal to 1. Use `BigInteger.longValueExact()` or `BigDecimal.longValueExact()` to detect lossy conversions if the source type supports them.

### Why don't intValue and longValue produce the same result?

The same `Number` can give different results depending on the target bit width:

~~~java
Number n = Long.valueOf(4_294_967_296L); // 2^32

System.out.println(n.intValue());  // 0
System.out.println(n.longValue()); // 4294967296
~~~

`intValue()` keeps the low 32 bits, which are all zeros; `longValue()` keeps the full 64-bit integer.

## 5. doubleValue(): converting to 64-bit double with only 53 bits of integer precision

`double` uses IEEE 754 binary64: 1 sign bit, 11 exponent bits, and 52 stored significand bits (plus 1 implicit leading bit for normal finite numbers). Thus its effective precision is **53 binary bits**, roughly equivalent to 15–17 significant decimal digits.

This has two consequences:

1. Every integer with magnitude at most **2^53 = 9,007,199,254,740,992** converts to `double` **exactly**. Larger numbers may still be exact if representable, but **consecutive integers are no longer guaranteed to be distinct**.
2. Large integers like `long` and `BigInteger` or decimals like `BigDecimal` can be **rounded**. `doubleValue()` does not throw an error for precision loss.

~~~java
Number exact = Long.valueOf(9_007_199_254_740_992L); // 2^53
Number next = Long.valueOf(9_007_199_254_740_993L);  // 2^53 + 1

System.out.println(exact.doubleValue() == next.doubleValue()); // true
~~~

Two adjacent `long` numbers round to the exact same `double` value. That is why you must not use `doubleValue()` as a lossless conversion for large IDs, large exact counters, or exact comparison keys.

### BigDecimal and decimals that cannot be represented exactly

~~~java
java.math.BigDecimal price = new java.math.BigDecimal("0.1");
double approximated = price.doubleValue();
System.out.println(approximated); // 0.1
~~~

The printed output is `0.1` because `Double.toString` picks a short decimal representation that round-trips to the same bits, **which does not mean 0.1 is stored exactly in binary**. If you must add money, compute taxes, or check exact decimal equality, keep calculations in `BigDecimal` and specify appropriate scale/rounding.

For extremely large `BigDecimal` or `BigInteger` values, `doubleValue()` can return `Double.POSITIVE_INFINITY` or `Double.NEGATIVE_INFINITY`; nonzero values very close to 0 can also round to `0.0` or `-0.0` when converting from `BigDecimal` to `double`. `double` does not have unlimited range or precision to hold every decimal number.

## 6. Complete runnable Java 17+ program

Create the file `NumberConversionsDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.BigInteger;

public class NumberConversionsDemo {
    public static void main(String[] args) {
        Number whole = Integer.valueOf(42);
        Number large = Long.valueOf(3_000_000_000L);
        Number fraction = Double.valueOf(-12.75);
        Number decimal = new BigDecimal("123.99");
        Number huge = new BigInteger("4294967303");

        System.out.println("Integer -> " + whole.intValue() + ", " +
                whole.longValue() + ", " + whole.doubleValue());
        System.out.println("Long -> " + large.intValue() + ", " +
                large.longValue() + ", " + large.doubleValue());
        System.out.println("Double -> " + fraction.intValue() + ", " +
                fraction.longValue() + ", " + fraction.doubleValue());
        System.out.println("BigDecimal -> " + decimal.intValue() + ", " +
                decimal.longValue() + ", " + decimal.doubleValue());
        System.out.println("BigInteger -> " + huge.intValue() + ", " +
                huge.longValue() + ", " + huge.doubleValue());

        System.out.println("NaN as int -> " + Double.valueOf(Double.NaN).intValue());
        System.out.println("Infinity as long -> " +
                Double.valueOf(Double.POSITIVE_INFINITY).longValue());

        try {
            ((BigDecimal) decimal).intValueExact();
        } catch (ArithmeticException ex) {
            System.out.println("Decimal exact -> ArithmeticException");
        }

        Number aboveExactDouble = new BigInteger("9007199254740993");
        BigDecimal roundedAsDecimal = BigDecimal.valueOf(aboveExactDouble.doubleValue());
        System.out.println("53-bit boundary -> " +
                aboveExactDouble.longValue() + " / " +
                roundedAsDecimal.toPlainString());
    }
}
~~~

Run:

~~~bash
javac NumberConversionsDemo.java
java NumberConversionsDemo
~~~

Output:

~~~text
Integer -> 42, 42, 42.0
Long -> -1294967296, 3000000000, 3.0E9
Double -> -12, -12, -12.75
BigDecimal -> 123, 123, 123.99
BigInteger -> 7, 4294967303, 4.294967303E9
NaN as int -> 0
Infinity as long -> 9223372036854775807
Decimal exact -> ArithmeticException
53-bit boundary -> 9007199254740993 / 9007199254740992
~~~

Notice:

- The value 3 billion converted to `int` yields a negative number due to the 32-bit limit.
- `-12.75` becomes `-12` in integer types because of truncation toward 0.
- `BigDecimal("123.99").intValue()` drops the fraction while `intValueExact()` detects the data loss.
- `2^32 + 7` converted to `int` leaves 7.
- `2^53 + 1` cannot be preserved exactly in `double`; the final printed line contrasts the original integer value with the rounded value obtained when converting through `double`.

## 7. Summary table of rules by object type

| Actual source | `intValue()` | `longValue()` | `doubleValue()` |
| --- | --- | --- | --- |
| `Byte` / `Short` / `Integer` | Exact if within `int` range; all these classes satisfy this | Exact | Exact for all `int` values |
| `Long` | Keeps low 32 bits; value may change | Exact | Can round for large integers |
| `Float` / `Double` | Truncates fraction; NaN → 0; overflow clamps to `int` bounds | Truncates fraction; NaN → 0; overflow clamps to `long` bounds | `Double` preserves value; `Float` widens the stored floating-point pattern to `double` exactly |
| `BigInteger` | Keeps low 32 bits | Keeps low 64 bits | Can round or become ±Infinity |
| `BigDecimal` | Drops fraction, can lose high bits | Drops fraction, can lose high bits | Can round, underflow, or overflow |

**Note on `Float.doubleValue()`:** Widening from `float` to `double` preserves the **binary value of the `float`** exactly, but does not recover decimal precision already lost when the number was stored as a `float`. For example:

~~~java
Number n = Float.valueOf(0.1f);
System.out.println(n.doubleValue()); // 0.10000000149011612
~~~

## 8. How to convert with data-loss checking

### With a long source

`Math.toIntExact(long)` returns `int` if within limits, otherwise throws `ArithmeticException`:

~~~java
long value = 50_000L;
int safe = Math.toIntExact(value);
System.out.println(safe); // 50000
~~~

### With a BigInteger or BigDecimal source

Use `intValueExact()` and `longValueExact()` instead of `intValue()`/`longValue()` when value truncation cannot be tolerated:

~~~java
java.math.BigDecimal amount = new java.math.BigDecimal("19.00");
System.out.println(amount.intValueExact()); // 19

java.math.BigDecimal bad = new java.math.BigDecimal("19.01");
try {
    System.out.println(bad.longValueExact());
} catch (ArithmeticException ex) {
    System.out.println("Has fractional part");
}
~~~

`19.00` has decimal digits in its representation, yet its **mathematical value is an integer**, so `intValueExact()` succeeds. Conversely, `19.01` cannot be converted to an exact `long`.

### With Double and Float

`Number` has no generic `intValueExact()`. If you truly must convert from `double` to an integer **with exact value and within limits**, check `Double.isFinite`, fractional part, range, and required exactness conditions before converting. Be especially careful at the `long` boundary: `(double) Long.MAX_VALUE` rounds up to 2^63 and no longer represents `Long.MAX_VALUE` exactly.

An explicit approach for finite `double` values is using `BigDecimal.valueOf(d).toBigIntegerExact()` to verify integrality of the **`double`'s round-trip decimal representation**, followed by `longValueExact()`/`intValueExact()` to check range. However, this approach **does not recover digits previously lost** when the data was converted into `double`. If the original input has decimal exactness (such as money), parse/store it as `BigDecimal` from the start.

## 9. When to pick intValue, longValue, or doubleValue?

| Need | Reasonable choice | What to verify |
| --- | --- | --- |
| Get a small count from `Number` | `intValue()` | Could fraction truncation or overflow occur? |
| Get a timestamp/integer ID in `long` range | `longValue()` | Is the source object truly an integer and within `long` range? |
| Perform floating-point math or measurements accepting error | `doubleValue()` | Is floating-point precision sufficient? |
| Convert `BigDecimal` to integer without data loss | `intValueExact()`/`longValueExact()` | Throws `ArithmeticException` if not exact |
| Convert `long` to `int` without overflow | `Math.toIntExact()` | Handle `ArithmeticException` |
| Monetary calculations needing exact decimals | Keep `BigDecimal` | Scale, rounding rules, comparisons |
| Integer calculations exceeding 64 bits | Keep `BigInteger` | Do not narrow to `int` or `long` unchecked |

Do not confuse **converting values** with **parsing strings**. `number.intValue()` applies only when you already have a `Number` object. An input `"123.45"` is a `String` and must be parsed appropriately first (such as `new BigDecimal("123.45")`); `Number` does not declare shared static `parse` or `valueOf` methods.

## 10. Polymorphism, null, and custom Number subclasses

An API may accept `Number` to work with multiple subclasses:

~~~java
static double twice(Number n) {
    if (n == null) {
        throw new IllegalArgumentException("Number must not be null");
    }
    return n.doubleValue() * 2;
}
~~~

The snippet above is an illustrative method, not a standalone program. Converting to `double` is appropriate if the API contract **permits approximation error**. If the API requires exactness for `BigDecimal` or `BigInteger`, an interface taking `Number` is too broad and calling `doubleValue()` blindly can lose data. In that case, choose a specific parameter type or document limits and conversion policies clearly.

A custom subclass extending `Number` must implement the four abstract methods; thus the general rules above describe **the standard `Number` classes**, and do not guarantee that every third-party subclass follows the same rounding, overflow, or conversion behavior.

## 11. Common mistakes

1. **Assuming `intValue()` checks for overflow.** False for `Long`, `BigInteger`, and `BigDecimal`. When exactness is required, use the corresponding `Exact` API.
2. **Assuming dropping the fraction is rounding.** `12.9` becomes `12` and `-12.9` becomes `-12`; apply an explicit rounding rule before converting if business logic requires it.
3. **Using `doubleValue()` for money or very large integer keys.** `double` can lose digits; prefer `BigDecimal`/`BigInteger`.
4. **Assuming NaN or Infinity throws an error when converted to integer.** For `Double` and `Float`, Java's conversion rules produce 0 or boundary values.
5. **Casting `Number` to a concrete class unconditionally.** `(BigDecimal) number` throws `ClassCastException` if the actual object is `Integer`, `Long`, or `Double`; check the type or design a stricter API.
6. **Confusing `Number` with string parsing.** Use an appropriate parser or constructor to create the numeric object first.
7. **Forgetting null.** Calling `n.intValue()` when `n == null` throws `NullPointerException`.

## 12. Self-check questions

**1.** Why does `Long.valueOf(4294967296L).intValue()` return `0`?

Because converting from 64 bits down to 32 bits keeps only the low 32 bits. `4294967296 = 2^32` has all-zero low 32 bits.

**2.** What does `Double.valueOf(-3.9).longValue()` return?

`-3L`, because converting floating-point to integer truncates the fractional part toward 0.

**3.** Can `new BigDecimal("123.45")` be replaced by `Double.valueOf(123.45)` in monetary processing and then calling `doubleValue()`?

It works syntactically, but decimal numbers may be approximated in binary64. When exactness is required for currency logic, keep `BigDecimal` with scale/rounding rules.

**4.** Why can `BigInteger.intValue()` and `Double.intValue()` follow different rules for large numbers?

Because `BigInteger` takes the low 32 bits of an arbitrary-precision integer; `Double` follows Java's floating-point-to-integer conversion, saturating at min/max when out of range.

**5.** To convert `BigDecimal("100.0")` to `int` and ensure no information is lost, what should you do?

Call `new BigDecimal("100.0").intValueExact()`; the result is `100` because its mathematical value is an exact integer, even though the representation includes one decimal place.

## 13. Key takeaways

- `Number` provides a common method interface for multiple numeric object types; **the actual object type determines** how conversion behaves.
- `intValue()` and `longValue()` return primitive integer values; they may truncate fractions, drop high bits, or saturate, **depending on the source type**.
- `doubleValue()` enables floating-point work but has a limit of **53 bits of effective precision** and can round, overflow to Infinity, or lose very small values.
- When data loss is unacceptable, check range and integrality; use `Math.toIntExact`, `BigInteger.intValueExact/longValueExact`, or `BigDecimal.intValueExact/longValueExact` according to the source type. Keep `BigDecimal`/`BigInteger` in calculations requiring high precision.
