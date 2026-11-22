# `BigInteger.ZERO`, `ONE`, `TWO`, `TEN`, and `valueOf` in Java

## 1. Overview: Large Integers and Creating Values

`java.math.BigInteger` represents **arbitrary-precision signed integers**. Unlike `int` (32 bits) and `long` (64 bits), the number of digits/bits of a `BigInteger` is not fixed at 32 or 64 bits. Practical limits come from memory, the range supported by the API/JVM, and computation resources.

A `BigInteger` is an **immutable object**. Every operation such as `add`, `multiply`, or `pow` returns a result value without modifying the original value.

To avoid recreating very commonly used integers, Java provides built-in `public static final` constants:

```java
import java.math.BigInteger;

BigInteger zero = BigInteger.ZERO; // 0
BigInteger one  = BigInteger.ONE;  // 1
BigInteger two  = BigInteger.TWO;  // 2
BigInteger ten  = BigInteger.TEN;  // 10
```

For another `long` integer, use:

```java
BigInteger n = BigInteger.valueOf(123456789L);
```

**Two core principles:**

1. Use the constants `ZERO`, `ONE`, `TWO`, `TEN` when matching those exact values and making code more readable; use `valueOf(long)` when the input is already an integer fitting in the `long` range.
2. Do not use the `==` operator to check whether **two `BigInteger` objects are equal in value**. Use `equals`, `compareTo`, or `signum` depending on the problem's semantics.

This lesson focuses on **the constants and the `valueOf` factory**, while covering all operations and pitfalls needed to use them accurately.

## 2. Four Built-In Constants

| Constant | Mathematical value | Typical usage |
| --- | ---: | --- |
| `BigInteger.ZERO` | 0 | Initializing sums, empty results, additive identity, checking for 0 |
| `BigInteger.ONE` | 1 | Multiplicative identity, starting products, incrementing/decrementing by one |
| `BigInteger.TWO` | 2 | Binary algorithms, computing powers of two, expressing factor 2 |
| `BigInteger.TEN` | 10 | Powers of 10, base-10 integer math, unit conversion |

Example inside a Java method:

```java
System.out.println(BigInteger.ZERO); // 0
System.out.println(BigInteger.ONE);  // 1
System.out.println(BigInteger.TWO);  // 2
System.out.println(BigInteger.TEN);  // 10
```

**Version note:** `BigInteger.TWO` appeared in **Java 9**. In Java 17 and later, all four constants are available. If forced to support Java 8, replace `TWO` with `BigInteger.valueOf(2)` or an equivalent expression.

Each constant is a `public static final` reference to an immutable `BigInteger` value. `final` here prevents reassigning the static field; the **immutability of `BigInteger` itself** prevents mutating the internal numeric value.

Do not treat `ZERO`, `ONE`, or `TEN` like global variables that can be directly added to or subtracted from:

```java
BigInteger sum = BigInteger.ZERO;
sum = sum.add(BigInteger.ONE); // sum holds the value 1

System.out.println(sum);             // 1
System.out.println(BigInteger.ZERO); // 0: original constant unchanged
```

The expression `sum.add(BigInteger.ONE)` creates or returns an object representing the result depending on library optimizations; regardless of the implementation, **the original value of `sum` is not modified** until we reassign the `sum` variable.

### The `ZERO` Constant Is Different from a `null` Reference

```java
BigInteger count = BigInteger.ZERO; // Valid number 0
BigInteger unknown = null;          // No object
```

`ZERO` is a real numeric value; `null` is not 0 and methods cannot be called on it. For example, `unknown.add(BigInteger.ONE)` throws `NullPointerException`. Use `BigInteger.ZERO` as a default only when business logic allows treating missing data as 0.

## 3. What Is `BigInteger.valueOf(long)`?

API signature:

```java
public static BigInteger valueOf(long val)
```

The method takes **a `long` integer value** and returns a `BigInteger` holding **that exact value**:

```java
BigInteger a = BigInteger.valueOf(0L);
BigInteger b = BigInteger.valueOf(42L);
BigInteger c = BigInteger.valueOf(-17L);
BigInteger d = BigInteger.valueOf(Long.MIN_VALUE);
```

`valueOf(long)` does not throw overflow because the input is already a valid `long`. **Every `long` value**, including `Long.MIN_VALUE` and `Long.MAX_VALUE`, is represented accurately by `BigInteger`.

Example:

```java
BigInteger min = BigInteger.valueOf(Long.MIN_VALUE);
BigInteger max = BigInteger.valueOf(Long.MAX_VALUE);

System.out.println(min); // -9223372036854775808
System.out.println(max); // 9223372036854775807
```

Calling with an `int` literal is valid thanks to **widening primitive conversion** from `int` to `long`:

```java
BigInteger x = BigInteger.valueOf(100); // int literal is converted to long
```

There is no `BigInteger.valueOf(double)` overload in this API. The following examples are **not** allowed:

```java
// BigInteger.valueOf(3.14);  // Compile error: double does not implicitly convert to long
// BigInteger.valueOf("42");  // Compile error: String is not a long
```

For strings, use the constructor `new BigInteger("42")`. For decimals with fractional parts or floating-point inputs, choose an explicit **rounding and precision policy** before converting to an integer.

### Use `valueOf` to Benefit from Object Reuse

The `valueOf` documentation recommends the static factory over a constructor taking `long` because it **may reuse frequently used `BigInteger` instances**. That means the JVM/library is free to optimize allocations where appropriate.

However, **this does not mean two calls to `BigInteger.valueOf(100)` must always return the same reference across every implementation**. What you must rely on is the **value** of the result:

```java
BigInteger a = BigInteger.valueOf(100);
BigInteger b = BigInteger.valueOf(100);

System.out.println(a.equals(b)); // true
```

Do not rely on `a == b`. Whether the factory returns the exact instance of `BigInteger.ZERO`, `ONE`, or another cached instance is not a contract for business value equality.

### When to Use Constants vs. `valueOf`?

- When writing algorithms with *fixed* values `0`, `1`, `2`, `10`, constants are usually clearer and avoid unnecessary factory calls.
- When the input is a `long` (method parameter, bounded integer parser data, or non-overflowing calculation), `BigInteger.valueOf(value)` is the standard choice.
- When the input is a decimal integer **that may exceed `long`**, parse from a string or compute directly with `BigInteger` — **do not** temporarily cast to `long` and then call `valueOf`.
- When needing results after `BigInteger` operations, use methods like `add`, `multiply`, `pow`, etc., rather than going back to `long`.

## 4. What `valueOf` Cannot Do: Widen Already-Overflowed Data

The biggest trap is doing math in `long` first and then converting to `BigInteger`:

```java
long max = Long.MAX_VALUE;
long overflowed = max + 1L;           // long integer overflow: becomes Long.MIN_VALUE
BigInteger wrong = BigInteger.valueOf(overflowed);

System.out.println(wrong); // -9223372036854775808
```

`BigInteger.valueOf` performed the **exact** conversion of the `long` value it received. It does not know the value before addition was `Long.MAX_VALUE`, and cannot recover lost bits.

The right approach is to **promote to `BigInteger` before addition exceeds the range**:

```java
BigInteger correct =
        BigInteger.valueOf(Long.MAX_VALUE).add(BigInteger.ONE);

System.out.println(correct); // 9223372036854775808
```

In other words:

\[
\operatorname{valueOf}(\text{overflowed long operation})
\ne
\text{direct BigInteger operation}.
\]

The same issue occurs with multiplication and exponentiation:

```java
long a = 4_000_000_000L;
long b = 4_000_000_000L;

// long product = a * b; // Exceeds Long.MAX_VALUE; overflows
BigInteger product = BigInteger.valueOf(a)
        .multiply(BigInteger.valueOf(b));

System.out.println(product); // 16000000000000000000
```

There is no "`long`-range overflow" in valid `BigInteger` results; limits still exist in resources and implementation constraints, but not a fixed 64-bit limit.

## 5. Numbers Exceeding `long`: Use the String Constructor

`BigInteger.valueOf` only takes a `long`. For integers larger than the `long` range, use:

```java
BigInteger huge = new BigInteger("100000000000000000000000000000000000000");
```

This constructor reads a decimal (base-10) string with an optional sign and does not route through `double` or `long`.

Example:

```java
BigInteger beyondLong = new BigInteger("9223372036854775808");

System.out.println(beyondLong);
// 9223372036854775808
```

For another radix, use `new BigInteger(text, radix)`:

```java
BigInteger hex = new BigInteger("FF", 16);
BigInteger binary = new BigInteger("1010", 2);

System.out.println(hex);    // 255
System.out.println(binary); // 10
```

`radix` must be within the supported range, normally `Character.MIN_RADIX` (2) through `Character.MAX_RADIX` (36). Malformed syntax or digits invalid for the radix cause `NumberFormatException`.

### Distinguishing Parsing and Type Conversion

| Input | Suitable API | Notes |
| --- | --- | --- |
| `long` | `BigInteger.valueOf(long)` | Accurately preserves the full `long` range |
| `int` | `BigInteger.valueOf(intValue)` | Java widens `int` to `long` |
| Decimal integer string | `new BigInteger(text)` | Does not go through `long` |
| Hexadecimal integer string | `new BigInteger(text, 16)` | E.g. `"FF"` → 255 |
| Existing `BigInteger` value | Use directly | Do not recreate unnecessarily |
| Decimal number like `"1.5"` | `BigDecimal` first, then integer conversion policy if needed | `new BigInteger("1.5")` is invalid |
| `double` | Do not use `BigInteger.valueOf(double)` | Must account for precision loss and rounding rules |

Reading `"9223372036854775808"` via `Long.parseLong` fails because it exceeds the `long` range, even though `BigInteger` reads it fine. This is why `Long.parseLong` should not be used as a "stepping stone" for large integer data.

## 6. Immutability and Operations with `ZERO`, `ONE`, `TWO`, `TEN`

`BigInteger`'s arithmetic methods return a new result **by value** without modifying operands:

```java
BigInteger x = BigInteger.TEN;
BigInteger y = x.add(BigInteger.ONE);

System.out.println(x); // 10
System.out.println(y); // 11
```

Some common operations:

| Operation | Java code | Result |
| --- | --- | --- |
| `7 + 1` | `BigInteger.valueOf(7).add(BigInteger.ONE)` | `8` |
| `7 - 1` | `BigInteger.valueOf(7).subtract(BigInteger.ONE)` | `6` |
| `7 × 2` | `BigInteger.valueOf(7).multiply(BigInteger.TWO)` | `14` |
| `7 × 10` | `BigInteger.valueOf(7).multiply(BigInteger.TEN)` | `70` |
| `2^10` | `BigInteger.TWO.pow(10)` | `1024` |
| `10^6` | `BigInteger.TEN.pow(6)` | `1000000` |
| Left shift 1 by 5 bits | `BigInteger.ONE.shiftLeft(5)` | `32` |
| Negate 10 | `BigInteger.TEN.negate()` | `-10` |
| Absolute value of -10 | `BigInteger.TEN.negate().abs()` | `10` |

`ZERO` is the additive identity: \(n+0=n\). `ONE` is the multiplicative identity: \(n\times1=n\). Do not infer from this a guarantee of **the same reference** if the library optimizes by returning one of the operands; numeric equality must be checked via `equals`.

Accumulation example:

```java
BigInteger sum = BigInteger.ZERO;

for (long value : new long[] { 1, 2, 3, 4 }) {
    sum = sum.add(BigInteger.valueOf(value));
}

System.out.println(sum); // 10
```

The reassignment `sum = sum.add(...)` is required. If you only call `sum.add(...)` without capturing the result, the value stored in `sum` does not change.

### Exponentiation and the `0^0` Case

`BigInteger.pow(int exponent)` accepts a **non-negative** `int` exponent:

```java
System.out.println(BigInteger.TWO.pow(10)); // 1024
System.out.println(BigInteger.TEN.pow(6));  // 1000000
System.out.println(BigInteger.ZERO.pow(0)); // 1
```

By API convention, `pow(0)` returns `ONE`, even when the base is `ZERO`. This is an **integer exponentiation programming convention**; in mathematical contexts, the expression `0^0` may be defined differently or left indeterminate. Do not apply an API convention without checking the application's mathematical model.

If `exponent < 0`, `BigInteger.pow` throws `ArithmeticException`: `2^-1` cannot be represented as a `BigInteger` integer. If the exponent is too large, the computation can consume excessive memory/time; validate work bounds for untrusted input.

## 7. Value Comparison: `equals`, `compareTo`, `signum` Instead of `==`

**`BigInteger` is a reference object**, not a primitive wrapper with auto-unboxing to `long`.

```java
BigInteger a = BigInteger.valueOf(10);
BigInteger b = BigInteger.TEN;

boolean equal = a.equals(b); // true
```

For two `BigInteger` references:

- `a == b` checks **same object**.
- `a.equals(b)` checks **same integer value**.
- `a.compareTo(b)` returns negative, 0, or positive corresponding to `a < b`, `a = b`, `a > b`.
- `a.signum()` returns `-1`, `0`, or `1` depending on the sign of the value.

Example:

```java
BigInteger a = BigInteger.valueOf(10);
BigInteger b = BigInteger.TEN;

System.out.println(a.equals(b));     // true
System.out.println(a.compareTo(b));  // 0
System.out.println(a.signum());      // 1
```

Do not use `==` even if one trial shows `BigInteger.valueOf(10) == BigInteger.TEN` is `true` in the running JVM. Caching/reuse is an implementation choice, **not the definition of integer equality**.

### Checking for Zero Properly

```java
BigInteger n = BigInteger.valueOf(0);

boolean isZero = n.signum() == 0;
boolean alsoZero = n.equals(BigInteger.ZERO);
```

Both check the **value** if `n` is non-null. When `n == null`, calling `signum()` or `equals()` throws `NullPointerException`. If you must handle nullable data:

```java
import java.util.Objects;

boolean zeroIfPresent = Objects.equals(n, BigInteger.ZERO);
```

This condition returns `false` when `n == null`, and `true` when `n` has value 0. If business logic needs to distinguish missing from zero, check `n == null` separately.

### Comparing with a Primitive

There is no auto-unboxing from `BigInteger` to `long`:

```java
BigInteger n = BigInteger.TEN;

// boolean wrong = (n == 10); // Does not compile: BigInteger and int are incompatible

boolean right = n.equals(BigInteger.valueOf(10));
```

When needing to compare a `BigInteger` with a `long`, create `BigInteger.valueOf(long)` to compare values, or use appropriate range checks/exact conversions. Do not cast `BigInteger` to `double` to compare if the number is very large.

## 8. `valueOf` and Allocation Optimization: Do Not Confuse with Wrapper Caching

The purpose of `valueOf` is to produce an exact value and **allow the library to reuse common objects**. Never infer that `valueOf` always allocates a new instance or always returns a unique singleton for every number.

Example:

```java
BigInteger x = BigInteger.valueOf(7);
BigInteger y = BigInteger.valueOf(7);

System.out.println(x.equals(y)); // true
// Do not build business logic on x == y.
```

A few notes:

1. `BigInteger.ZERO`, `ONE`, `TWO`, `TEN` are **built-in constants** for convenience and clarity, not a complete *interning* mechanism for all numbers.
2. `BigInteger.valueOf(long)` may optimize object creation; `==` cannot be relied upon to tell two numbers apart.
3. Also do not use a `BigInteger` as a **synchronization monitor/lock** expecting each `valueOf` call to create an independent lock: instances may be shared. Use a dedicated `new Object()` owned by the application when a lock is needed.
4. Because `BigInteger` is immutable, constants can be shared in many places without worrying that `add`/`multiply` will mutate them.
5. `BigInteger` performance differs from `long` operations: larger bit counts increase computation work and can introduce object allocations/GC pressure. Use it when a range beyond primitives is needed or when an API requires it.

Choose `BigInteger` for **correctness and value range**, not out of belief that `valueOf` references are always fixed.

## 9. Converting from `BigInteger` to Primitives and Data Loss

`BigInteger` extends `Number` and provides primitive extraction methods:

```java
BigInteger n = BigInteger.valueOf(42);

int asInt = n.intValue();
long asLong = n.longValue();
double asDouble = n.doubleValue();
```

However, `intValue()`/`longValue()` **do not guarantee out-of-range detection**; they can discard high-order bits when narrowing to an integer type. `doubleValue()` can also round or return infinity if the magnitude is too large.

Example:

```java
BigInteger beyondLong =
        BigInteger.valueOf(Long.MAX_VALUE).add(BigInteger.ONE);

long truncated = beyondLong.longValue();
System.out.println(truncated); // -9223372036854775808
```

If you need **guaranteed intactness**, use:

```java
long exact = BigInteger.valueOf(42).longValueExact();
int exactInt = BigInteger.valueOf(42).intValueExact();
```

For out-of-range numbers, `longValueExact()`/`intValueExact()` throw `ArithmeticException`:

```java
BigInteger tooBig = BigInteger.TWO.pow(80);

// tooBig.longValueExact(); // ArithmeticException
```

Catch or propagate the exception according to the method's contract instead of silently losing data. These exact APIs are especially important when large integer data must go into a protocol or DB that only supports 64 bits.

**Safety in one conversion direction does not guarantee safety in the reverse direction:** `BigInteger.valueOf(long)` is always exact, whereas `someBigInteger.longValue()` can lose information.

## 10. Complete Java 17 Demo

Save the program as `BigIntegerConstantsDemo.java`:

```java
import java.math.BigInteger;

public class BigIntegerConstantsDemo {
    public static void main(String[] args) {
        System.out.println("ZERO = " + BigInteger.ZERO);
        System.out.println("ONE = " + BigInteger.ONE);
        System.out.println("TWO = " + BigInteger.TWO);
        System.out.println("TEN = " + BigInteger.TEN);

        BigInteger fromLong = BigInteger.valueOf(-17L);
        BigInteger fromString = new BigInteger("9223372036854775808");

        System.out.println("valueOf(-17) = " + fromLong);
        System.out.println("string > long max = " + fromString);

        BigInteger next = BigInteger.valueOf(Long.MAX_VALUE)
                .add(BigInteger.ONE);
        System.out.println("max long + ONE = " + next);

        BigInteger ten = BigInteger.TEN;
        BigInteger eleven = ten.add(BigInteger.ONE);
        System.out.println("TEN after add = " + ten);
        System.out.println("TEN + ONE = " + eleven);

        System.out.println("TWO^10 = " + BigInteger.TWO.pow(10));
        System.out.println("TEN^6 = " + BigInteger.TEN.pow(6));
        System.out.println("TWO^100 = " + BigInteger.TWO.pow(100));
        System.out.println("ZERO^0 = " + BigInteger.ZERO.pow(0));

        BigInteger anotherZero = BigInteger.valueOf(0);
        System.out.println("zero equals = "
                + BigInteger.ZERO.equals(anotherZero));
        System.out.println("zero signum = " + anotherZero.signum());
        System.out.println("compare ZERO to ONE = "
                + BigInteger.ZERO.compareTo(BigInteger.ONE));

        System.out.println("hex FF = " + new BigInteger("FF", 16));

        try {
            BigInteger.TWO.pow(80).longValueExact();
            System.out.println("Unexpected successful narrowing");
        } catch (ArithmeticException ex) {
            System.out.println("longValueExact: ArithmeticException");
        }
    }
}
```

Compile/run:

```bash
javac BigIntegerConstantsDemo.java
java BigIntegerConstantsDemo
```

Output:

```text
ZERO = 0
ONE = 1
TWO = 2
TEN = 10
valueOf(-17) = -17
string > long max = 9223372036854775808
max long + ONE = 9223372036854775808
TEN after add = 10
TEN + ONE = 11
TWO^10 = 1024
TEN^6 = 1000000
TWO^100 = 1267650600228229401496703205376
ZERO^0 = 1
zero equals = true
zero signum = 0
compare ZERO to ONE = -1
hex FF = 255
longValueExact: ArithmeticException
```

The demo makes no assumptions about `==` on `BigInteger` objects, does not route large numeric strings through `long`, and uses `longValueExact()` to detect out-of-range data when converting back to a primitive.

## 11. Real-World Scenarios: Constants Make Code Express Intent

### Summing Without Overflow

```java
BigInteger total = BigInteger.ZERO;

for (long item : new long[] { Long.MAX_VALUE, 1L, 2L }) {
    total = total.add(BigInteger.valueOf(item));
}

System.out.println(total); // 9223372036854775810
```

Here the addition **is performed entirely in `BigInteger`**. Using `long total` to accumulate first and converting later would overflow.

### Counting Possibilities by Doubling

```java
BigInteger count = BigInteger.ONE;

for (int i = 0; i < 10; i++) {
    count = count.multiply(BigInteger.TWO);
}

System.out.println(count); // 1024
```

For non-negative integer `n`, `BigInteger.TWO.pow(n)` usually expresses this more concisely than a loop. Remember `pow` takes an `int` exponent; if `n` is huge, the result can consume significant resources.

### Creating Exact Powers of 10

```java
BigInteger million = BigInteger.TEN.pow(6);
System.out.println(million); // 1000000
```

Do not replace this with `(long) Math.pow(10, n)` for arbitrary `n` when wanting **unbounded exact integers**: `Math.pow` works on `double`, so it is subject to floating-point range/precision and casting can lose data.

### Converting an Integer Value by Smallest Unit

If you have a total quantity as a `BigInteger`, you can multiply accurately by `TEN`, `TWO`, or other constants:

```java
BigInteger units = BigInteger.valueOf(500);
BigInteger subunits = units.multiply(BigInteger.TEN);

System.out.println(subunits); // 5000
```

For units of measure or currency, conversion factors must come from business rules. `TEN` is simply the number 10, not inherently a "smallest currency unit" or "measurement unit."

## 12. Common Mistakes

| Mistake | Why it is wrong | Right approach |
| --- | --- | --- |
| `BigInteger.valueOf("123")` | `valueOf` takes `long`, not `String` | `new BigInteger("123")` |
| Creating numbers beyond `long` with `valueOf` | Cannot pass a value exceeding `long` range | Parse from string or compute in `BigInteger` first |
| `BigInteger.valueOf(Long.MAX_VALUE + 1L)` | Addition overflows while still `long` | `BigInteger.valueOf(Long.MAX_VALUE).add(BigInteger.ONE)` |
| `a == b` with two `BigInteger`s | Compares references rather than values | `a.equals(b)` or `a.compareTo(b) == 0` |
| Thinking `ZERO` is `null` | `ZERO` is an object holding 0 | Handle missing data state separately |
| `sum.add(n);` without reassignment | `BigInteger` is immutable | `sum = sum.add(n);` |
| `new BigInteger("1.5")` | Constructor expects an integer in a radix | Use `BigDecimal` if there is a fractional part |
| Calling `longValue()` on arbitrary values | May drop high bits | `longValueExact()` to fail fast |
| Calling `doubleValue()` when exact integer needed | `double` can round large integers | Keep `BigInteger` or check range/precision |
| Relying on identity from `valueOf` cache | Object reuse is not the equality rule | Compare by value |
| Using `Math.pow` then casting to `long` | Floating point can lose digits/overflow | `BigInteger.pow` with non-negative integer exponent |
| Expecting `+`, `*` operators to work on `BigInteger` | Not a primitive number supporting those operators | Call `add`, `multiply` |
| Using `BigInteger.TWO` in Java 8 | `TWO` did not exist in Java 8 | Java 9+, or `valueOf(2)` |
| Treating large integers as infinite resources | `BigInteger` still has memory/time limits | Validate input/exponent size |

### Two Additional Notes on Performance and APIs

**Do not mechanically use `BigInteger` for every small counter.** If the value range is known to stay within `long` and arithmetic has appropriate overflow checks, primitives are usually simpler and faster. Use `BigInteger` when needing a range beyond primitives, exactness beyond primitive limits, or when an API/protocol requires it.

**Do not use `BigInteger` as a shared synchronization monitor based on the factory.** Because `valueOf` can reuse instances, another piece of code might receive the same object; use a private lock owned by the application when synchronization is needed.

## 13. Exercises and Answers

**Question 1.** In Java 17, what numbers do the four constants `BigInteger.ZERO`, `ONE`, `TWO`, `TEN` represent? Which constant did not exist in Java 8?

**Answer:** 0, 1, 2, and 10 respectively. `BigInteger.TWO` was introduced in Java 9 so it cannot be used directly on Java 8.

**Question 2.** Given:

```java
BigInteger n = BigInteger.TEN;
n.add(BigInteger.ONE);
System.out.println(n);
```

What is the output, and why?

**Answer:** `10`. `BigInteger` is immutable; calling `add` returns the result without modifying `n`. To get `11`, assign `n = n.add(BigInteger.ONE)`.

**Question 3.** How do you compute `Long.MAX_VALUE + 1` accurately using `BigInteger`?

**Answer:**

```java
BigInteger result =
        BigInteger.valueOf(Long.MAX_VALUE).add(BigInteger.ONE);
```

Do not perform `long` addition before calling `valueOf`.

**Question 4.** Is `BigInteger.valueOf(10).equals(BigInteger.TEN)` `true` or `false`? Do you need to check `==` to be sure?

**Answer:** `true`. `equals` compares integer values; `==` is unnecessary and inappropriate for determining numeric equality.

**Question 5.** To read the number `"123456789012345678901234567890"` into a `BigInteger`, which API do you use?

**Answer:** `new BigInteger("123456789012345678901234567890")`; do not use `Long.parseLong` or `BigInteger.valueOf(String)`.

**Question 6.** What do `BigInteger.TWO.pow(10)` and `BigInteger.TEN.pow(6)` return?

**Answer:** `1024` and `1000000` respectively, both as `BigInteger` objects holding exact integer values.

**Question 7.** What does `BigInteger.ZERO.pow(0)` return per the Java API? Should it be applied unconditionally to every mathematical problem?

**Answer:** It returns `BigInteger.ONE` (value 1) per API convention. Some mathematical contexts treat `0^0` as indeterminate; follow the problem's definition.

**Question 8.** Why is `BigInteger.TWO.pow(80).longValue()` unsuitable if the application needs the full value? What is the alternative method?

**Answer:** The value `2^80` exceeds the `long` range; `longValue()` can drop high bits, causing data loss. `longValueExact()` throws `ArithmeticException` to signal it cannot convert exactly.

**Question 9.** A program always calls `BigInteger.valueOf(7)` and compares references to determine "whether two IDs are equal." What is wrong here?

**Answer:** Numeric values can serve as IDs, but comparing references based on object reuse is flawed design. Compare using `equals`, or define an ID class with an appropriate value-comparison contract.

**Question 10.** What does `new BigInteger("FF", 16)` give? Is `new BigInteger("FF")` equivalent?

**Answer:** The first gives `255` in base 16. The second uses base 10 by default, so `"FF"` is invalid and throws `NumberFormatException`.

**Key takeaway:** `BigInteger.ZERO`, `ONE`, `TWO`, `TEN` are readable immutable integer constants; `BigInteger.valueOf(long)` constructs exact values from `long` and allows reuse optimizations. Do not perform potentially overflowing `long` operations before converting; do not compare `BigInteger`s with `==`; and keep data as `BigInteger` when needing to distinguish integers beyond primitive limits.