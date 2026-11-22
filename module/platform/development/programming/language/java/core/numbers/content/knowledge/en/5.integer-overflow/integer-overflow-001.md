# Integer Overflow and Wrap-Around Behavior in Java

In Java, **integer overflow** occurs when the mathematical result of an operation falls outside the representable range of the integer type performing the operation. For ordinary addition, subtraction, and multiplication on `int` or `long`, Java retains the fixed-width bit pattern. As a result, the value can **wrap around** from the largest positive value to the smallest negative value, or in the reverse direction, **without an automatic exception**.

Typical example:

```java
int max = Integer.MAX_VALUE; // 2147483647
int wrapped = max + 1;       // -2147483648, does not throw an exception
```

The two declarations above are illustrative code placed inside a Java method. The exact mathematical value of `2_147_483_647 + 1` is `2_147_483_648`, but an `int` addition cannot hold that value. To understand why the result turns negative, we need to look at **type limits, two's complement bit patterns, and conversion order**.

## 1. Ranges of Integer Types

| Type | Width | Minimum Value | Maximum Value |
| --- | ---: | ---: | ---: |
| `byte` | 8-bit signed | -128 | 127 |
| `short` | 16-bit signed | -32_768 | 32_767 |
| `int` | 32-bit signed | -2_147_483_648 | 2_147_483_647 |
| `long` | 64-bit signed | -9_223_372_036_854_775_808 | 9_223_372_036_854_775_807 |

Java's signed integer types use **two's complement representation**. For a `w`-bit type, the value range is from `-2^(w-1)` to `2^(w-1) - 1`. One bit is reserved for the sign meaning; there is one more negative value than positive values.

Commonly used constants for boundary checks include `Byte.MIN_VALUE`, `Short.MAX_VALUE`, `Integer.MIN_VALUE`, `Integer.MAX_VALUE`, `Long.MIN_VALUE`, and `Long.MAX_VALUE`. `char` is also a 16-bit primitive type, but it is **unsigned** (0–65_535) and mainly holds UTF-16 code units; you must not blindly apply the signed range of `short` to `char`.

**The range of the operands determines the operation**, not the name of the variable receiving the result. Therefore, you must ask "is the operation running in `int` or `long`?" before considering the target variable.

## 2. Wrap-Around Mechanism from Two's Complement Bit Patterns

In ordinary integer addition, subtraction, and multiplication, Java uses the lower bits of the result represented in the target width; in terms of unsigned values, this is arithmetic modulo `2^32` for `int` and modulo `2^64` for `long`. Afterward, that same bit pattern is interpreted according to the **signed** type.

32-bit example at the boundary:

```text
Integer.MAX_VALUE =  2147483647 = 0x7FFFFFFF
                     +         1
------------------------------------------------
New 32-bit pattern:               0x80000000
Signed int value:                -2147483648
```

The highest bit (bit 31) flips from `0` to `1`. For the pattern `0x8000_0000`, two's complement interprets it as `Integer.MIN_VALUE`. Therefore:

```java
int a = Integer.MAX_VALUE + 1; // Integer.MIN_VALUE
int b = Integer.MIN_VALUE - 1; // Integer.MAX_VALUE
int c = -Integer.MIN_VALUE;    // Integer.MIN_VALUE
```

These are valid illustrative declarations inside a method. The third case is special: `int` has no positive value `2_147_483_648`, so negating `Integer.MIN_VALUE` with the `-` operator yields the original value again.

One way to model a mathematical result `R` becoming an `int` value is: keep `R` modulo `2^32`, and if bit 31 equals 1, subtract `2^32` to read it as signed. For `long`, replace `2^32` with `2^64`. This is a way to **explain the wrap-around behavior**; it does not mean Java automatically turns `int` into an unsigned type.

In Java, this phenomenon is well-defined for integers rather than a random machine-dependent outcome. Even so, **defined behavior does not mean a business-correct result**: a monetary total, quantity, buffer size, or timestamp unexpectedly becoming negative is still an application bug.

## 3. Overflow in Addition, Subtraction, Multiplication, and Negation

| Operation | Mathematical Result | Java `int` Result |
| --- | ---: | ---: |
| `Integer.MAX_VALUE + 1` | 2_147_483_648 | -2_147_483_648 |
| `Integer.MIN_VALUE - 1` | -2_147_483_649 | 2_147_483_647 |
| `100_000 * 100_000` | 10_000_000_000 | 1_410_065_408 |
| `-Integer.MIN_VALUE` | 2_147_483_648 | -2_147_483_648 |

With multiplication, the expression `100_000 * 100_000` uses two `int` values, so the multiplication itself also runs in `int`; the true value of 10 billion lies outside the 32-bit range. Java keeps the lower bit pattern, so the multiplication yields `1_410_065_408`. If an application stores item quantity × unit price in an `int`, the result will be wrong even when both individual operands are completely valid.

A similar phenomenon occurs with `long`:

```java
long afterMax = Long.MAX_VALUE + 1L; // Long.MIN_VALUE
long beforeMin = Long.MIN_VALUE - 1L; // Long.MAX_VALUE
```

**`long` only increases the range to 64 bits**; it does not eliminate overflow permanently. Notably, `Math.abs(Integer.MIN_VALUE)` still returns `Integer.MIN_VALUE` (a negative value), because there is no corresponding positive `int`; similarly, `Math.abs(Long.MIN_VALUE)` returns `Long.MIN_VALUE`. If you need to catch the error, Java 17 provides `Math.negateExact` or `Math.absExact` to throw `ArithmeticException` when the result cannot be represented.

## 4. Assigning to `long` After an `int` Operation Does Not Fix an Overflowed Result

A common bug-inducing case:

```java
long wrong = 2_000_000_000 + 1_000_000_000;
long right = 2_000_000_000L + 1_000_000_000;
```

- On the `wrong` line, **both operands are `int`**, so the `int` addition overflows to `-1_294_967_296`; only afterward does Java widen that result to `long`. The result is still a negative number.
- On the `right` line, the `L` suffix makes one operand a `long`. The remaining `int` operand is promoted to `long` before the addition, so you get the correct `3_000_000_000L`.

The result also depends on **cast placement**:

```java
long tooLate = (long) (100_000 * 100_000);  // 1410065408L
long correct1 = ((long) 100_000) * 100_000; // 10000000000L
long correct2 = 100_000L * 100_000;        // 10000000000L
```

In `tooLate`, the parentheses force multiplication in `int` first; `(long)` only receives the already-overflowed result. The two `correct` lines convert at least one operand to `long` **before multiplying**.

Ordinary addition, subtraction, or multiplication of two `byte`/`short`/`char` values is also promoted to **`int`**. For example, `byte a = 127; byte b = 1; int c = a + b;` gives `c == 128`, because the addition runs in `int`. However, `byte a = 127; a++;` brings `a` back to `-128` because the increment converts the result back to `byte`. Therefore, you must distinguish overflow when computing in `int` from **narrowing conversion** down to a smaller type.

## 5. Arithmetic Overflow, Out-of-Range Literals, and Narrowing Casts Are Three Different Situations

| Situation | Example | What Happens |
| --- | --- | --- |
| Invalid decimal literal directly in source code | `long x = 3_000_000_000;` | **Compile error**: literal without `L` exceeds the `int` range |
| Valid operands whose operation overflows | `int x = Integer.MAX_VALUE + 1;` | **Compiles**, result is `Integer.MIN_VALUE` |
| `int` operation overflows then widens | `long x = 2_000_000_000 + 1_000_000_000;` | **Compiles**, produces an already-wrong negative `long` value |
| Narrowing cast losing bits | `byte x = (byte) 128;` | **Compiles**, `x == -128` |
| Numeric string out of range when parsing | `Integer.parseInt("2147483648")` | **Throws `NumberFormatException`**, does not wrap around |

This table is important when diagnosing issues: if a direct literal is out of range, the program **cannot run**; however, when two valid numbers produce a sum that is too large, ordinary integer arithmetic can **run and return a wrong value**. In the case of an explicit narrowing cast, Java keeps the lower bits according to the target width; that is a potentially lossy type conversion, not the exact same cause as addition overflow.

Another point: **constant expressions** can be evaluated by Java at compile time and still produce a wrapped-around result. For example, `int wrapped = 2_147_483_647 + 1;` is still valid and equals `-2_147_483_648`. Do not assume that "evaluated at compile time" means an overflow error will be reported. Active overflow detection relies on explicit checks or checked APIs.

## 6. Important Exception: `MIN_VALUE / -1` Division

Integer division differs from addition, subtraction, and multiplication. Normally, dividing by **0** throws `ArithmeticException`. However, Java has one division case that **exceeds the range without throwing an error**:

```java
int q = Integer.MIN_VALUE / -1; // Integer.MIN_VALUE
long r = Long.MIN_VALUE / -1L;  // Long.MIN_VALUE
```

The mathematical value of `Integer.MIN_VALUE / -1` is `2_147_483_648`, which cannot be represented as an `int`; Java's rule returns `Integer.MIN_VALUE` itself. The same applies to `long`. The remainder in this case is **0**.

Therefore, you should not say "integer division always detects overflow." When computing with signed integers—and especially when `MIN_VALUE` can occur—you must check `dividend == MIN_VALUE && divisor == -1` if you require an exact mathematical result guaranteed to be in range. Use a wider type (if there is enough room) or `BigInteger` to represent the mathematical quotient.

## 7. Standalone Compilable and Runnable Java 17+ Program

Create the file **`IntegerOverflowDemo.java`**:

```java
import java.math.BigInteger;

public class IntegerOverflowDemo {
    public static void main(String[] args) {
        int max = Integer.MAX_VALUE;
        int min = Integer.MIN_VALUE;
        long longMax = Long.MAX_VALUE;

        System.out.println("intMax=" + max);
        System.out.println("intMaxPlusOne=" + (max + 1));
        System.out.println("intMinMinusOne=" + (min - 1));
        System.out.println("negatedIntMin=" + (-min));
        System.out.println("productInInt=" + (100_000 * 100_000));
        System.out.println("lateWidening=" + (2_000_000_000 + 1_000_000_000));
        System.out.println("earlyLong=" + (2_000_000_000L + 1_000_000_000));
        System.out.println("longMaxPlusOne=" + (longMax + 1L));
        System.out.println("intMinDivMinusOne=" + (min / -1));
        System.out.println("narrowByte=" + ((byte) 128));
        System.out.println("wrappedBits=" + Integer.toHexString(max + 1));
        System.out.println("unsignedMinusOne=" + Integer.toUnsignedString(-1));
        System.out.println("unsignedCompare=" + Integer.compareUnsigned(-1, max));

        try {
            System.out.println(Math.addExact(max, 1));
        } catch (ArithmeticException ex) {
            System.out.println("addExact=overflow detected");
        }

        try {
            System.out.println(Math.multiplyExact(100_000, 100_000));
        } catch (ArithmeticException ex) {
            System.out.println("multiplyExact=overflow detected");
        }

        try {
            System.out.println(Math.negateExact(min));
        } catch (ArithmeticException ex) {
            System.out.println("negateExact=overflow detected");
        }

        try {
            System.out.println(Math.toIntExact(3_000_000_000L));
        } catch (ArithmeticException ex) {
            System.out.println("toIntExact=overflow detected");
        }

        BigInteger beyondLong =
                BigInteger.valueOf(longMax).add(BigInteger.ONE);
        System.out.println("beyondLong=" + beyondLong);
    }
}
```

Compile and run:

```bash
javac --release 17 -encoding UTF-8 IntegerOverflowDemo.java
java IntegerOverflowDemo
```

Stdout output (verified when executed):

```text
intMax=2147483647
intMaxPlusOne=-2147483648
intMinMinusOne=2147483647
negatedIntMin=-2147483648
productInInt=1410065408
lateWidening=-1294967296
earlyLong=3000000000
longMaxPlusOne=-9223372036854775808
intMinDivMinusOne=-2147483648
narrowByte=-128
wrappedBits=80000000
unsignedMinusOne=4294967295
unsignedCompare=1
addExact=overflow detected
multiplyExact=overflow detected
negateExact=overflow detected
toIntExact=overflow detected
beyondLong=9223372036854775808
```

Explanation of the key results:

- `intMaxPlusOne` and `intMinMinusOne` illustrate wrapping across both 32-bit boundaries; `negatedIntMin` illustrates that the smallest negative value has no corresponding positive counterpart.
- `productInInt`, `lateWidening`, and `earlyLong` show that overflow happens **in the operation's type**, independent of the receiving variable.
- `longMaxPlusOne` confirms that 64-bit arithmetic also has boundaries; `intMinDivMinusOne` illustrates the special division rule.
- `narrowByte=-128` is an example of **narrowing conversion**; `wrappedBits=80000000` shows the 32-bit pattern after adding `1` to the largest value.
- `unsignedMinusOne=4294967295` is only an **unsigned interpretation** of the `int` bit pattern `-1`, with no extra storage capacity; `unsignedCompare=1` means `-1` is considered greater than `Integer.MAX_VALUE` **in unsigned order**.
- The four `Exact` methods actively throw `ArithmeticException` in unrepresentable cases; `BigInteger` can hold results larger than `Long.MAX_VALUE`.

## 8. Detecting Overflow with `Math.*Exact` Methods

When the business requirement is to **detect overflow instead of receiving a wrapped-around result**, use the checked methods:

| API | When Useful |
| --- | --- |
| `Math.addExact(a, b)` | Detecting overflow when adding `int` or `long` |
| `Math.subtractExact(a, b)` | Detecting overflow when subtracting `int` or `long` |
| `Math.multiplyExact(a, b)` | Detecting overflow when multiplying `int` or `long` |
| `Math.incrementExact(a)` / `decrementExact(a)` | Incrementing/decrementing a counter without silently wrapping around |
| `Math.negateExact(a)` / `absExact(a)` | Handling sign negation and absolute value at the smallest negative boundary |
| `Math.toIntExact(longValue)` | Converting `long` to `int` while reporting an error when out of range |

These methods throw **`ArithmeticException`** when the result cannot be represented in the return type. For example:

```java
int count = 2_147_483_647;
int next = Math.incrementExact(count); // Throws ArithmeticException.
```

This is a snippet to place inside a method. If the application needs error handling, place the call in a `try/catch` block or let the exception be handled at an appropriate layer. Note that `Math.addExact(int, int)` checks the **`int`** range, even when the result is assigned to a `long` variable. To add in 64 bits, convert at least one operand to `long` **before calling** the `long` overload:

```java
long sum = Math.addExact(2_000_000_000L, 1_000_000_000L); // 3000000000
```

The `Exact` methods operate only on the operation being called. If a subexpression has already overflowed earlier, they **cannot recover the data**:

```java
long wrong = Math.addExact((long) (Integer.MAX_VALUE + 1), 0L);
// Result is still -2147483648: int overflow occurred before the call.

long right = Math.addExact((long) Integer.MAX_VALUE, 1L);
// Exact result: 2147483648.
```

## 9. Checking Boundaries Before the Operation

If you do not use the `Exact` functions, you can sometimes check boundaries before adding, for example when **`delta` is non-negative**:

```java
static int addNonNegativeExact(int current, int delta) {
    if (delta < 0) {
        throw new IllegalArgumentException("delta must be nonnegative");
    }
    if (current > Integer.MAX_VALUE - delta) {
        throw new ArithmeticException("int overflow");
    }
    return current + delta;
}
```

This is a **method** that must be placed inside a Java class. Because `delta` has been verified to be non-negative, `Integer.MAX_VALUE - delta` is safe within the `int` range; if `current` exceeds the allowed threshold, the addition will overflow. For adding two arbitrary numbers that may be negative or positive, using `Math.addExact` is usually less error-prone than constructing multiple boundary conditions yourself.

Real-world cases where overflow should be treated as an error rather than normal wrap-around: calculating monetary totals, counting records, calculating array/buffer sizes, summing inventory quantities, totaling bytes, file sizes, or checking input limits. For example, if code computes `items * bytesPerItem` using `int` and then uses the result to allocate memory, an overflowed product can turn into a negative number or a positive number that is too small. Use `Math.multiplyExact` and check practical limits before allocating.

## 10. When Should You Use `long`, `BigInteger`, or Unsigned APIs?

**Choose `long`** when the result can exceed the `int` range, but is provably within the `long` range. The key condition is converting types **before the operation**:

```java
int quantity = 100_000;
int unit = 100_000;
long total = (long) quantity * unit; // 10000000000
```

**Choose `BigInteger`** when the result can be larger than `Long.MAX_VALUE` or smaller than `Long.MIN_VALUE`. For example:

```java
java.math.BigInteger result =
        java.math.BigInteger.valueOf(Long.MAX_VALUE)
                .add(java.math.BigInteger.ONE);
// result == 9223372036854775808.
```

`BigInteger` stores integers with precision limited only by available memory; you must use methods such as `add`, `subtract`, and `multiply`, because `+` and `*` operators are not overloaded for Java objects. When converting back to `long` or `int`, use `longValueExact()` / `intValueExact()` when you want to detect out-of-range values.

**Use `Integer.toUnsignedString`, `Integer.toUnsignedLong`, `Integer.compareUnsigned`, `Long.toUnsignedString`** when the input specification explicitly states that the data is an **unsigned bit pattern** (for example, binary formats or protocols). These APIs change how a bit pattern is **interpreted, compared, divided, or displayed**, rather than making ordinary `int` addition capable of holding larger signed numbers. You should not use unsigned APIs merely to "mask" overflow in signed business calculations.

## 11. Signs of Overflow in Real Programs

Suspect overflow when you observe behaviors such as:

- An increasing `int` counter suddenly becomes negative or the smallest negative number.
- The sum of two positive numbers returns a negative number or a result smaller than each term.
- A product `quantity * price` differs from the expected result even though all input values are valid.
- A `long` variable receives a negative result from an expression composed **entirely of `int`s**.
- A condition depending on increasing order, such as `next > current`, unexpectedly fails at the boundary.
- `Math.abs` on the minimum value still returns a negative number.

Distinguish these from **deliberate modulo-based designs**, such as certain hash functions, bit-manipulation algorithms, circular counters, or protocols specifying 32-bit integers. When modulo behavior is an actual requirement, document the desired bit width and bit pattern explicitly; when exact arithmetic is required, detect overflow.

In testing, you should test **just below the boundary, right at the boundary, and immediately after an operation that crosses the boundary**. For example, `Integer.MAX_VALUE - 1`, `Integer.MAX_VALUE`, and `Integer.MAX_VALUE + 1`; also test `Integer.MIN_VALUE`, negation, subtracting 1, multiplying large numbers, and `Long.MAX_VALUE` values. Do not try to write an out-of-range decimal literal to test overflow: doing so only tests **compile-time literal errors**, not the runtime behavior of operations.

## 12. Common Misconceptions

| Misconception | Why It Is Wrong | How to Handle It |
| --- | --- | --- |
| `int` automatically throws an error when adding past the limit | Ordinary `+` uses fixed-width integers and wraps around | Use `Math.addExact` when you want detection |
| `long x = a * b;` is always safe if `x` is `long` | If `a` and `b` are `int`, the multiplication can overflow in `int` | `long x = (long) a * b;` |
| Casting `(long)` around an already-overflowed expression fixes the result | The cast happens after the inner operation | Cast one operand beforehand |
| `long` never overflows | `long` has a finite 64-bit width | `Math.*Exact` or `BigInteger` |
| `Math.abs(Integer.MIN_VALUE)` is always non-negative | The corresponding positive value exceeds `int` | `Math.absExact`, `long`, or `BigInteger` as required |
| Dividing by `-1` is always representable | `MIN_VALUE / -1` exceeds the range yet returns `MIN_VALUE` | Check the special case |
| `Integer.parseInt("2147483648")` wraps around | Parsing checks the range and throws an error | Use `Long.parseLong` if appropriate |
| Narrowing cast `(byte)128` is the same as an `int` addition bug | That is a narrowing conversion keeping the low bits | Check boundaries or use exact conversion APIs |
| Unsigned APIs make `int` wider | Those APIs only change how the bit pattern is read | Use a sufficiently wide type for exact calculation |

## 13. Self-Check Questions

1. **What is `Integer.MAX_VALUE + 1`?** `Integer.MIN_VALUE`, because the 32-bit pattern wraps around to having the sign bit equal to 1.
2. **What is `Integer.MIN_VALUE - 1`?** `Integer.MAX_VALUE`, due to wrapping past the lower boundary.
3. **What is `long total = 2_000_000_000 + 1_000_000_000;`?** `-1_294_967_296L`, because the addition overflowed in `int` before widening.
4. **How do you get the correct `3_000_000_000`?** `2_000_000_000L + 1_000_000_000` or cast one operand to `long` before adding.
5. **What is `long x = Long.MAX_VALUE + 1L;`?** `Long.MIN_VALUE`; use `Math.addExact(Long.MAX_VALUE, 1L)` if an exception is needed.
6. **Is every overflow caused by the `+` operator?** No: subtraction, multiplication, negation, and the `MIN_VALUE / -1` case all have boundaries to consider.
7. **Can an `int` store `2_147_483_648` directly as a signed value?** No; use `long`. If you need to keep a 32-bit pattern as unsigned, you must make that interpretation explicit.
8. **When should you use `BigInteger`?** When the required result range exceeds `long` or arbitrary-precision integer arithmetic is needed.

**Remember:** in Java, ordinary integer operations can **wrap around modulo the bit width without reporting an error**. To avoid unintended inaccuracies, determine the type of **each operand before the operation**, choose `long` when its range suffices, use `Math.*Exact` or boundary checks when overflow must be detected, and use `BigInteger` if the requirement exceeds even `long`.
