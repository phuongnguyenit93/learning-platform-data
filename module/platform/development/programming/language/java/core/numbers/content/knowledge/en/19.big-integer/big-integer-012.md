# BigInteger: How `intValue` and `longValue` Differ from `intValueExact` and `longValueExact`

In Java Core, `java.math.BigInteger` represents **arbitrary-precision signed integers**, which can be far larger than the 32-bit limit of `int` and the 64-bit limit of `long`. When passing a `BigInteger` value into an API that accepts only primitives, you must explicitly choose **whether data loss is allowed or not**.

The easily confused method pairs:

- **`intValue()` / `longValue()`:** convert to the narrower type by **keeping the low bits**. If the value is too large or too small, the result can lose high bits, flip sign, or wrap to 0; these methods **do not report out-of-range overflow**.
- **`intValueExact()` / `longValueExact()`:** require the integer value **to fit completely within the range** of the target type. If it cannot be represented exactly, they throw **`ArithmeticException`** rather than silently truncating bits.

Key example:

```java
BigInteger n = new BigInteger("4294967296"); // 2^32.
int unsafe = n.intValue();           // 0: all 32 low bits are 0.
long safeLong = n.longValueExact();  // 4294967296L: still fits in long.
// int impossible = n.intValueExact(); // Throws ArithmeticException.
```

This is a snippet that can be placed inside a method of a class importing `java.math.BigInteger`. This lesson covers **two's complement bit narrowing**, boundaries `Integer.MIN_VALUE/MAX_VALUE` and `Long.MIN_VALUE/MAX_VALUE`, negative numbers, `2^32`, `2^64`, using `Exact` methods, and designing APIs that do not silently drop data.

## 1. Why Convert `BigInteger` to `int` or `long`?

`BigInteger` provides arbitrary-precision integer arithmetic like `add`, `subtract`, `multiply`, `pow`, `shiftLeft`, and supports numbers far beyond `long`. Yet many other Java APIs accept `int` or `long`:

- Indices, counts, sizes, and parameters in several libraries require `int`.
- Timestamps, counters, or byte counts with a broad enough range typically use `long`.
- Protocols with fixed 32-bit or 64-bit fields require choosing a type, range, and overflow policy.
- Databases have `INTEGER`/`BIGINT` columns with limits you must obey.

**Converting does not change the value inside the original `BigInteger` object.** It only produces a primitive result. If bits are lost in conversion, the exact data still remains in the `BigInteger` object, while the `int`/`long` variable holding the result carries a **different value**.

```java
BigInteger big = BigInteger.ONE.shiftLeft(64);
long narrowed = big.longValue(); // 0L
System.out.println(big);         // 18446744073709551616: object unchanged.
```

Do not treat a "successful conversion" as proof that the number fits in range. Both `intValue()` and `longValue()` are designed to support **intentional truncation**, not range parsing or validation.

## 2. Four Key Methods and Their Contracts

| Method | Result | Outside target type range | Use when |
| --- | --- | --- | --- |
| `BigInteger.intValue()` | 32-bit `int` | Keeps **low 32 bits**, may change value and sign; no overflow error | Intentionally extracting low 32 bits |
| `BigInteger.longValue()` | 64-bit `long` | Keeps **low 64 bits**, may change value and sign; no overflow error | Intentionally extracting low 64 bits |
| `BigInteger.intValueExact()` | 32-bit `int` | Throws **`ArithmeticException`** | Needing exact conversion within signed `int` range |
| `BigInteger.longValueExact()` | 64-bit `long` | Throws **`ArithmeticException`** | Needing exact conversion within signed `long` range |

All are **instance methods** called on a `BigInteger` object. The two methods with the `Exact` suffix belong to the `BigInteger` class API, not methods available on every variable typed as `Number`.

```java
BigInteger value = BigInteger.valueOf(42);
int a = value.intValue();          // 42
int b = value.intValueExact();     // 42
long c = value.longValue();        // 42L
long d = value.longValueExact();   // 42L
```

**Within the representable range**, both variants for the same type return **the exact same result**. The difference emerges once values exceed signed 32/64-bit limits.

## 3. Signed Integer Ranges to Know by Heart

Fixed limits in Java:

| Type | Bits | Minimum value | Maximum value |
| --- | ---: | ---: | ---: |
| `int` | 32 | `-2^31 = -2147483648` | `2^31 - 1 = 2147483647` |
| `long` | 64 | `-2^63 = -9223372036854775808` | `2^63 - 1 = 9223372036854775807` |
| `BigInteger` | Arbitrary | No `int`/`long` limit | Only resource and relevant implementation limits |

For `intValueExact()`, the validity condition is:

```text
Integer.MIN_VALUE <= value <= Integer.MAX_VALUE
```

For `longValueExact()`:

```text
Long.MIN_VALUE <= value <= Long.MAX_VALUE
```

If a `BigInteger` exceeds **only the `int` range** while still fitting in `long`, then `intValueExact()` fails while **`longValueExact()` succeeds**. For instance, `2^31` or `2^32` are valid `long` numbers, but not valid signed `int`s.

Avoid treating `Integer.MAX_VALUE` and `Long.MAX_VALUE` as if they were the largest positive magnitudes Java in general can store. They are limits **of their corresponding signed primitive types**.

## 4. `intValue()`: Low 32 Bits, No Overflow Check

The meaning of `intValue()` can be understood via **32-bit two's complement**: take the integer value modulo `2^32`, then interpret that bit pattern as signed `int`.

Let:

```text
r = value mod 2^32, with 0 <= r < 2^32
```

Then:

```text
intValue(value) =
    r                 if 0 <= r < 2^31
    r - 2^32          if 2^31 <= r < 2^32
```

Examples:

```java
BigInteger a = BigInteger.valueOf(Integer.MAX_VALUE).add(BigInteger.ONE);
// a = 2147483648 = 2^31.
int narrowedA = a.intValue(); // -2147483648 = Integer.MIN_VALUE.

BigInteger b = BigInteger.ONE.shiftLeft(32);
// b = 4294967296 = 2^32.
int narrowedB = b.intValue(); // 0.
```

At `2^31`, the low 32 bits are `0x80000000`, which `int` reads as the smallest negative number. At `2^32`, all 32 low bits are 0, so the result is 0. **This is not saturation to `Integer.MAX_VALUE` or an exception**.

Illustrative table:

| Original `BigInteger` | `intValue()` | `intValueExact()` |
| ---: | ---: | --- |
| 123 | 123 | 123 |
| 2147483647 | 2147483647 | 2147483647 |
| 2147483648 | **-2147483648** | `ArithmeticException` |
| -2147483648 | -2147483648 | -2147483648 |
| -2147483649 | **2147483647** | `ArithmeticException` |
| 4294967295 | **-1** | `ArithmeticException` |
| 4294967296 | **0** | `ArithmeticException` |
| -4294967296 | **0** | `ArithmeticException` |

The row `-2147483649 → 2147483647` shows that **negative values smaller than `Integer.MIN_VALUE`** can also turn positive after keeping only low bits.

## 5. `longValue()`: Keeps Low 64 Bits, Same Rule

For `long`, replace 32 with 64:

```text
r = value mod 2^64, with 0 <= r < 2^64

longValue(value) =
    r                 if 0 <= r < 2^63
    r - 2^64          if 2^63 <= r < 2^64
```

This is the mathematical model of keeping the **low 64 bits**, then interpreting them as signed `long` two's complement.

```java
BigInteger a = BigInteger.valueOf(Long.MAX_VALUE).add(BigInteger.ONE);
// a = 9223372036854775808 = 2^63.
long narrowedA = a.longValue(); // Long.MIN_VALUE.

BigInteger b = BigInteger.ONE.shiftLeft(64);
// b = 18446744073709551616 = 2^64.
long narrowedB = b.longValue(); // 0L.
```

The `longValue` and `longValueExact` variants also differ at the negative boundary. `Long.MIN_VALUE - 1` becomes `Long.MAX_VALUE` when keeping the low 64 bits, rather than throwing on `longValue()`.

| Original `BigInteger` | `longValue()` | `longValueExact()` |
| ---: | ---: | --- |
| 9223372036854775807 | 9223372036854775807 | 9223372036854775807 |
| 9223372036854775808 | **-9223372036854775808** | `ArithmeticException` |
| -9223372036854775808 | -9223372036854775808 | -9223372036854775808 |
| -9223372036854775809 | **9223372036854775807** | `ArithmeticException` |
| 18446744073709551615 | **-1** | `ArithmeticException` |
| 18446744073709551616 | **0** | `ArithmeticException` |

**Remember:** `longValue()` is not a safe way to clamp an oversized integer to the nearest `long` representative. It is a **low 64 bits** conversion that can completely alter the value.

## 6. A Number Fitting `long` but Not `int`

Consider `4294967296 = 2^32`:

```java
BigInteger n = new BigInteger("4294967296");

int a = n.intValue();           // 0: loses all significant bits above 32 bits.
long b = n.longValue();         // 4294967296L.
long c = n.longValueExact();    // 4294967296L.
// n.intValueExact();           // ArithmeticException.
```

Because this number fits exactly in `long`, **there is no reason to turn it into 0 just to squeeze it into `int`**. If the API accepts `long`, use `longValueExact()`. If the API strictly requires `int`, apply an **explicit policy**: reject, split work into chunks, or paginate; never silently pass 0.

Silently returning 0 is especially dangerous for fields like **record counts to process**, **memory limits**, **file lengths**, **order quantities**, or **identifiers**. A huge value after bit truncation can become 0, negative, or a small plausible-looking number.

## 7. `intValueExact()`: Checked Signed 32-Bit Conversion

`BigInteger.intValueExact()` succeeds only when the value already lies in **`[-2^31, 2^31-1]`**. If out of range, it throws `ArithmeticException`.

```java
BigInteger a = BigInteger.valueOf(123);
int ok = a.intValueExact(); // 123.

BigInteger b = BigInteger.valueOf(Integer.MAX_VALUE).add(BigInteger.ONE);
// int wrong = b.intValueExact(); // ArithmeticException.
```

This includes **both positive and negative overflow**. Not only huge positive numbers fail: `Integer.MIN_VALUE - 1` also exceeds `int` range.

Use it whenever being off by even a single unit is unacceptable, such as passing a `BigInteger` into a library's `int` field or handing an exact calculation result to a 32-bit-bounded system.

Exceptions can be handled:

```java
static int requireInt(BigInteger value) {
    try {
        return value.intValueExact();
    } catch (ArithmeticException ex) {
        throw new IllegalArgumentException(
                "Value outside signed 32-bit range", ex);
    }
}
```

This is an **example method** placed inside a class importing `BigInteger`. Depending on the system, you can keep `ArithmeticException`, translate it into a domain exception, or return a result type with an error code. Never catch the exception and **fall back to `intValue()`**, as that defeats all overflow checking.

## 8. `longValueExact()`: Checked Signed 64-Bit Conversion

`BigInteger.longValueExact()` works similarly but checks the wider range: **`[-2^63, 2^63-1]`**.

```java
BigInteger x = BigInteger.valueOf(Long.MAX_VALUE);
long ok = x.longValueExact(); // Long.MAX_VALUE.

BigInteger tooLarge = BigInteger.ONE.shiftLeft(63);
// long broken = tooLarge.longValueExact(); // ArithmeticException.
```

For `2^63`, `longValue()` returns `Long.MIN_VALUE`; `longValueExact()` throws an exception. For `-2^63` (`Long.MIN_VALUE` itself), the exact version **succeeds**, since that is a valid lower bound.

If values exceed 64 bits and the system genuinely needs **exact integers**, keep `BigInteger` in the API, use suitable libraries/database columns, or design multi-part storage. Do not assume `long` is wide enough just because data is "rarely large."

## 9. `Exact` Methods Check Value, Not String Representation

`BigInteger` stores an **integer value**, not the verbatim input string. Two strings such as `"+00042"` and `"42"` parse to the same value 42; `intValueExact()` returns 42 in both cases.

```java
BigInteger a = new BigInteger("42");
BigInteger b = new BigInteger("+00042");
System.out.println(a.equals(b)); // true.
System.out.println(b.intValueExact()); // 42.
```

Hence `intValueExact()` is **not** an input format validator, nor can it detect leading zeros, extra plus signs, or rule violations in an identifier. If an input must preserve exact characters like leading zeros, it is likely a **code/identifier** rather than an arithmetic number; keep `String` and validate its schema separately.

Likewise, the word `Exact` does not mean the method checks business rules like "must be non-negative" or "quantity <= 1000": a negative `int` is still exactly representable and returned normally.

## 10. `intValue()` Is Not Casting `BigInteger` with a Cast Operator

In Java, `BigInteger` is an **object**, not a `long` or `int` primitive. You cannot write:

```java
BigInteger big = BigInteger.ONE.shiftLeft(32);
// int value = (int) big; // Does not compile: BigInteger cannot be cast directly to int.
```

You must call one of the conversion methods:

```java
int lowBits = big.intValue(); // Intentionally drops high bits.
long checked = big.longValueExact(); // Requires exact fit.
```

The bit-truncation model of `BigInteger.intValue()` matches **primitive narrowing conversion** on low-order bits in outcome, yet the syntax and source type are completely different. Do not treat `BigInteger` as a `long` wrapper that can be cast normally.

Moreover, `BigInteger.longValue()` **does not call `intValueExact()` or `longValueExact()`**. If you want to catch data loss, you must explicitly pick the **Exact variant**.

## 11. Negative Numbers and How Low Bits Behave

Negative `BigInteger`s have two's complement semantics during bitwise operations. When narrowing to 32/64 bits, it **does not take absolute value and truncate**, but takes the low bits of the **signed value**.

Example:

```java
BigInteger a = BigInteger.ONE.shiftLeft(32).negate(); // -4294967296.
int bits32 = a.intValue(); // 0.
long whole64 = a.longValueExact(); // -4294967296.
```

Because `-2^32` is divisible by `2^32`, all low 32 bits are 0. This does not turn the original value into zero; only the **information transferred into `int`** is zero.

An example near the negative boundary:

```java
BigInteger x = BigInteger.valueOf(Integer.MIN_VALUE)
        .subtract(BigInteger.ONE); // -2147483649.
int narrowed = x.intValue(); // 2147483647.
```

The `int` version produces a large positive number even though the original was negative. This can break business logic such as:

```java
int amount = someBigInteger.intValue();
if (amount > 0) {
    // Can enter this branch even when the original BigInteger was negative and very small.
}
```

When a value serves as a **length, count, monetary amount, or non-negative quantity**, use `intValueExact()` combined with checking **the `>= 0` condition** before or after (since exact only checks range, not domain).

## 12. `2^32`, `2^64`, and the "Wraps to 0" Rule

Two clearest boundary landmarks for low-bits conversion:

```java
BigInteger p32 = BigInteger.ONE.shiftLeft(32);
BigInteger p64 = BigInteger.ONE.shiftLeft(64);

System.out.println(p32.intValue());  // 0.
System.out.println(p32.longValue()); // 4294967296.

System.out.println(p64.intValue());  // 0.
System.out.println(p64.longValue()); // 0.
```

At `2^32`, all **low 32 bits** are 0, while the low 64 bits still carry `2^32`. At `2^64`, both low 32-bit and low 64-bit portions are 0.

Conversely:

```java
BigInteger p64MinusOne = BigInteger.ONE.shiftLeft(64)
        .subtract(BigInteger.ONE);

System.out.println(p64MinusOne.longValue()); // -1.
```

An all-1s low 64-bit pattern is read by **signed** `long` as -1. Even though a positive integer can print `longValue() == -1`, that does not mean `BigInteger` "lost its sign" in the original calculation; it is **the signed interpretation of a bit pattern**.

## 13. Huge Values Can Still Yield Small Results

A `BigInteger` can be enormous yet become a small number when truncated to its low 32/64 bits. Example:

```java
BigInteger huge = BigInteger.ONE.shiftLeft(100)
        .add(BigInteger.valueOf(123));

System.out.println(huge.intValue());  // 123.
System.out.println(huge.longValue()); // 123.
```

Reason: `2^100` is divisible by `2^64`, so the **low 64 bits** of `2^100 + 123` leave only 123. This strongly illustrates that a **plausible-looking** `intValue()` or `longValue()` result does not prove it reflects the real value.

If after conversion the program checks `result <= limit` without checking range **beforehand**, an oversized input can turn into a small number below the limit. Use the `Exact` variant whenever **value preservation is required**, especially on limit-checking, allocation, and work-routing paths.

## 14. Comparison with `Math.toIntExact(long)`

The JDK has the method:

```java
int narrowed = Math.toIntExact(someLong);
```

It checks whether a value **that is already a `long`** fits in signed `int`. You cannot pass a `BigInteger` directly to `Math.toIntExact`.

These two approaches have different meanings:

```java
BigInteger big = new BigInteger("4294967296");

// Right way when needing BigInteger -> exact int:
// int safe = big.intValueExact(); // ArithmeticException.

// Roundabout via long with checking:
// long first = big.longValueExact(); // Succeeds because 2^32 fits in long.
// int second = Math.toIntExact(first); // ArithmeticException.
```

For values outside signed 64 bits, **you must call `longValueExact()`** in the first step. If `longValueExact()` is replaced with `longValue()`, data is already truncated, and `Math.toIntExact` checks only the **corrupted post-truncation value**, unable to recover the original value.

Dangerous example:

```java
BigInteger p64 = BigInteger.ONE.shiftLeft(64);
long brokenLong = p64.longValue(); // 0.
int seemsFine = Math.toIntExact(brokenLong); // 0, NO exception.
```

`Math.toIntExact` is correct for input `long 0`, yet that was already wrong data if the goal was to represent `BigInteger 2^64` accurately. When the source is `BigInteger`, calling **`intValueExact()` directly** is both clearer and safer.

## 15. Comparison with `byteValueExact()` and `shortValueExact()`

Alongside signed `int`/`long`, `BigInteger` also has narrowing methods:

```java
byte a = BigInteger.valueOf(127).byteValueExact(); // 127.
short b = BigInteger.valueOf(32767).shortValueExact(); // 32767.

// BigInteger.valueOf(128).byteValueExact();   // ArithmeticException.
// BigInteger.valueOf(32768).shortValueExact(); // ArithmeticException.
```

Applicable bounds:

| Type | Signed range |
| --- | --- |
| `byte` | -128..127 |
| `short` | -32768..32767 |
| `int` | -2147483648..2147483647 |
| `long` | -9223372036854775808..9223372036854775807 |

Conversely, `byteValue()` and `shortValue()` can also truncate bits when narrowing. When parsing a fixed-width protocol field, distinguish:

- **Signed value** within Java's primitive type range.
- **Unsigned bit pattern** of the field, e.g., unsigned byte 0..255 or unsigned int 0..2^32-1.

A `BigInteger` value `255` **does not fit in a signed byte**, so `byteValueExact()` must throw an exception. If the protocol genuinely expects writing byte `FF` meaning **unsigned 255**, that is an **unsigned encoding with a different range check**, not an exact conversion to signed `byte`.

## 16. Unsigned Data Case: Do Not Confuse with Signed Exact

Java `int` and `long` are **signed** integer types. `BigInteger.intValueExact()` is not meant to accept 32-bit unsigned values up to `2^32-1`; it only allows signed `int` up to `2^31-1`.

Example:

```java
BigInteger unsigned32Max = new BigInteger("4294967295");
int lowBits = unsigned32Max.intValue(); // -1.
long positive = unsigned32Max.longValueExact(); // 4294967295L.
```

Here:

- If you need the **exact positive value**, keep `BigInteger` or convert to `long` via `longValueExact()`.
- If you need the **32-bit pattern** of an unsigned field, you may use `intValue()` **after verifying** the value lies in `0..2^32-1`; the receiver must use unsigned APIs such as `Integer.toUnsignedLong` or `Integer.toUnsignedString` to interpret it.
- **Do not** use `intValueExact()` as an unsigned 32-bit range validator, because +4294967295 is unsigned-valid yet does not fit signed `int`.

Similarly, `BigInteger` `2^64-1` returns -1 from `longValue()`, while `longValueExact()` throws an error because it is not a valid signed `long`. If a protocol stores unsigned 64-bit values, validate `0..2^64-1` separately and clearly define how to handle the **`long` bit pattern** or keep `BigInteger`.

## 17. Clear Signed/Unsigned Validation Snippets

For a signed `BigInteger` value needing to go into `int`:

```java
static int requireSignedInt(BigInteger value) {
    return value.intValueExact();
}
```

For an **unsigned 32-bit** field needing to hold its bit pattern in `int`:

```java
static int requireUnsignedIntBits(BigInteger value) {
    BigInteger max = BigInteger.ONE.shiftLeft(32).subtract(BigInteger.ONE);
    if (value.signum() < 0 || value.compareTo(max) > 0) {
        throw new ArithmeticException("outside unsigned 32-bit range");
    }
    return value.intValue(); // Intentional: only extract the low 32 bits.
}
```

These two methods are **code snippets inside a Java class**, not built-in APIs. The unsigned version **validates before truncating bits**, because after truncation there is no longer enough information to tell whether the original value was too large or too small.

This is a classic case where `intValue()` is **right** if and only if:

1. The goal is genuinely a **32-bit representation** rather than a signed `int` value.
2. The unsigned range has been explicitly checked.
3. Downstream code consumes the result with **unsigned semantics**, never accidentally comparing against 0 as signed.

Do not apply the unsigned strategy to task counts, array indices, or money just to avoid exceptions—those domains usually require **non-negative signed values within specific ranges**.

## 18. Pre-Checking with `compareTo` When Business Messages Are Needed

If you want to distinguish "too small" from "too large," instead of catching `ArithmeticException` you can check directly:

```java
static int requireIntWithMessage(BigInteger value) {
    BigInteger min = BigInteger.valueOf(Integer.MIN_VALUE);
    BigInteger max = BigInteger.valueOf(Integer.MAX_VALUE);
    if (value.compareTo(min) < 0) {
        throw new IllegalArgumentException("below Integer.MIN_VALUE");
    }
    if (value.compareTo(max) > 0) {
        throw new IllegalArgumentException("above Integer.MAX_VALUE");
    }
    return value.intValueExact();
}
```

This is an illustrative method that can be placed inside a class importing `BigInteger`. In production code, `min`/`max` can be stored as reusable `static final` constants.

**Why still call `intValueExact()` after checking?** It clearly expresses the invariant being maintained: the method returns an `int` only if the value fits. After checking with `compareTo`, `intValue()` gives the same result, yet using `Exact` communicates API semantics with less ambiguity.

Do not replace the range condition with `value.bitLength() <= 31` without analyzing negative numbers and boundaries, because `BigInteger.bitLength()` has specific rules for negative values. Comparing directly against `Integer.MIN_VALUE/MAX_VALUE` is clearer and less error-prone.

## 19. An Exception Is Not Always a Bug to "Fix" by Removing Checks

The two `Exact` methods **throw `ArithmeticException` intentionally**. When that happens, review:

- **Data source:** is the input within the problem's domain?
- **Target type:** is `int`/`long` mandatory or can `BigInteger` be kept?
- **Business limit:** an integer fitting in `long` might still exceed quotas/resources.
- **Representation:** is the data a signed number or an unsigned bit pattern?
- **Caller response:** should you return an error code, a domain exception, or require a smaller value?

Code to avoid:

```java
static int dangerousFallback(BigInteger x) {
    try {
        return x.intValueExact();
    } catch (ArithmeticException ex) {
        return x.intValue(); // WRONG if exact conversion is required.
    }
}
```

If business logic intentionally needs **wrap modulo 2^32**, choose `intValue()` from the outset and document why. If business logic wants to **clamp/saturate** to `Integer.MIN_VALUE/MAX_VALUE`, write a separate clamping policy after comparison; `intValue()` **does not perform saturation**.

## 20. Standalone Runnable Java 17+ Program

Create file **`BigIntegerConversionDemo.java`**:

```java
import java.math.BigInteger;

public class BigIntegerConversionDemo {
    private static String exactInt(BigInteger value) {
        try {
            return Integer.toString(value.intValueExact());
        } catch (ArithmeticException ex) {
            return "ArithmeticException";
        }
    }

    private static String exactLong(BigInteger value) {
        try {
            return Long.toString(value.longValueExact());
        } catch (ArithmeticException ex) {
            return "ArithmeticException";
        }
    }

    private static void show(String label, BigInteger value) {
        System.out.println(label + " value=" + value);
        System.out.println(label + " int=" + value.intValue()
                + ", intExact=" + exactInt(value));
        System.out.println(label + " long=" + value.longValue()
                + ", longExact=" + exactLong(value));
    }

    public static void main(String[] args) {
        show("small", BigInteger.valueOf(123));
        show("intMax", BigInteger.valueOf(Integer.MAX_VALUE));
        show("intOver", BigInteger.valueOf(Integer.MAX_VALUE).add(BigInteger.ONE));
        show("intUnder", BigInteger.valueOf(Integer.MIN_VALUE).subtract(BigInteger.ONE));
        show("twoPow32", BigInteger.ONE.shiftLeft(32));
        show("minusTwoPow32", BigInteger.ONE.shiftLeft(32).negate());
        show("longMax", BigInteger.valueOf(Long.MAX_VALUE));
        show("longOver", BigInteger.valueOf(Long.MAX_VALUE).add(BigInteger.ONE));
        show("longUnder", BigInteger.valueOf(Long.MIN_VALUE).subtract(BigInteger.ONE));
        show("twoPow64", BigInteger.ONE.shiftLeft(64));
        show("twoPow64MinusOne", BigInteger.ONE.shiftLeft(64).subtract(BigInteger.ONE));
        show("twoPow100Plus123", BigInteger.ONE.shiftLeft(100).add(BigInteger.valueOf(123)));

        BigInteger outsideInt = new BigInteger("4294967295");
        boolean fitsInt = outsideInt.compareTo(BigInteger.valueOf(Integer.MIN_VALUE)) >= 0
                && outsideInt.compareTo(BigInteger.valueOf(Integer.MAX_VALUE)) <= 0;
        System.out.println("fitsInt=" + fitsInt);
        System.out.println("mathToIntExactError="
                + exactMathToInt(BigInteger.ONE.shiftLeft(32).longValueExact()));
        System.out.println("bigIntegerUnchanged="
                + BigInteger.ONE.shiftLeft(64).equals(new BigInteger("18446744073709551616")));
    }

    private static String exactMathToInt(long value) {
        try {
            return Integer.toString(Math.toIntExact(value));
        } catch (ArithmeticException ex) {
            return "ArithmeticException";
        }
    }
}
```

Compile and run:

```bash
javac --release 17 -encoding UTF-8 BigIntegerConversionDemo.java
java BigIntegerConversionDemo
```

Exact stdout (compiled and run on Java 17):

```text
small value=123
small int=123, intExact=123
small long=123, longExact=123
intMax value=2147483647
intMax int=2147483647, intExact=2147483647
intMax long=2147483647, longExact=2147483647
intOver value=2147483648
intOver int=-2147483648, intExact=ArithmeticException
intOver long=2147483648, longExact=2147483648
intUnder value=-2147483649
intUnder int=2147483647, intExact=ArithmeticException
intUnder long=-2147483649, longExact=-2147483649
twoPow32 value=4294967296
twoPow32 int=0, intExact=ArithmeticException
twoPow32 long=4294967296, longExact=4294967296
minusTwoPow32 value=-4294967296
minusTwoPow32 int=0, intExact=ArithmeticException
minusTwoPow32 long=-4294967296, longExact=-4294967296
longMax value=9223372036854775807
longMax int=-1, intExact=ArithmeticException
longMax long=9223372036854775807, longExact=9223372036854775807
longOver value=9223372036854775808
longOver int=0, intExact=ArithmeticException
longOver long=-9223372036854775808, longExact=ArithmeticException
longUnder value=-9223372036854775809
longUnder int=-1, intExact=ArithmeticException
longUnder long=9223372036854775807, longExact=ArithmeticException
twoPow64 value=18446744073709551616
twoPow64 int=0, intExact=ArithmeticException
twoPow64 long=0, longExact=ArithmeticException
twoPow64MinusOne value=18446744073709551615
twoPow64MinusOne int=-1, intExact=ArithmeticException
twoPow64MinusOne long=-1, longExact=ArithmeticException
twoPow100Plus123 value=1267650600228229401496703205499
twoPow100Plus123 int=123, intExact=ArithmeticException
twoPow100Plus123 long=123, longExact=ArithmeticException
fitsInt=false
mathToIntExactError=ArithmeticException
bigIntegerUnchanged=true
```

Notable lines:

1. **`small` and `intMax`**: within signed `int` range, all four methods return values compatible with target type sizes.
2. **`intOver`**: +2147483648 becomes -2147483648 with `intValue()`, whereas `intValueExact()` throws; `longValueExact()` still succeeds.
3. **`intUnder`**: -2147483649 becomes +2147483647 when truncated to `int`; exact method rejects it.
4. **`twoPow32`, `minusTwoPow32`**: original values ±4294967296 produce `intValue() == 0`, even though they fit signed `long`.
5. **`longOver`, `longUnder`**: one step past 64-bit bounds causes wrap-around conversion in `longValue()`, whereas `longValueExact()` throws an exception.
6. **`twoPow64`**: `BigInteger` (`2^{64}`) has `intValue() == 0` and `longValue() == 0`, not because the original number is zero.
7. **`twoPow64MinusOne`**: maximum 64-bit unsigned value yields `longValue() == -1`; exact method rejects it because it exceeds signed `long`.
8. **`twoPow100Plus123`**: a `BigInteger` with over 30 digits has both `intValue()` and `longValue()` equal to 123, showing how truncated results can look valid.
9. **`fitsInt=false`**, **`mathToIntExactError=ArithmeticException`**, and **`bigIntegerUnchanged=true`**: demonstrate range checking, `Math.toIntExact`, and `BigInteger` immutability.

In the example, `exactInt` and `exactLong` **catch `ArithmeticException` to print test output**. Real applications typically propagate the error or handle it per business rules instead of turning it into a string. The entire program uses only the JDK 17 standard library.

## 21. Distinguishing Other Methods with "Exact" in Their Names

Java has multiple APIs with the `Exact` suffix, which should not be lumped into a single behavior:

| API | Job |
| --- | --- |
| `BigInteger.intValueExact()` | Converts `BigInteger` to signed `int` **with range checking** |
| `BigInteger.longValueExact()` | Converts `BigInteger` to signed `long` **with range checking** |
| `Math.toIntExact(long)` | Converts **`long`** to `int` with range checking |
| `Math.addExact(int,long...)` | Group of primitive addition methods checking overflow per overload |
| `Math.multiplyExact(...)` | Primitive multiplication with overflow checking |
| `BigDecimal.intValueExact()` | Converts **decimal** to `int`, checking both exact integer representability and range |
| `BigDecimal.longValueExact()` | Converts decimal to `long`, also disallowing loss of fractional part |

For `BigInteger`, **there is no fractional part** to round when converting to `int` or `long`; only value range needs checking. For `BigDecimal`, `intValueExact` can also fail when a value like `1.5` is not an integer, even though its magnitude is tiny. This is an important distinction if a system uses `Number`-typed variables or mixes `BigInteger` and `BigDecimal`.

Example:

```java
BigInteger a = new BigInteger("1");
int x = a.intValueExact(); // 1, valid.

java.math.BigDecimal b = new java.math.BigDecimal("1.5");
// b.intValueExact() throws ArithmeticException because .5 cannot be dropped exactly.
```

The `Exact` suffix must be understood according to **each API's contract**, not as a blanket promise that every downstream operation is also exact.

## 22. Essential Boundary Tests

To ensure your program does not truncate data unintentionally, test at least:

| Test value | Expected `intValueExact` | Expected `longValueExact` |
| --- | --- | --- |
| 0, 1, -1 | Succeeds | Succeeds |
| `Integer.MAX_VALUE` | Succeeds | Succeeds |
| `Integer.MAX_VALUE + 1` | **Error** | Succeeds |
| `Integer.MIN_VALUE` | Succeeds | Succeeds |
| `Integer.MIN_VALUE - 1` | **Error** | Succeeds |
| `Long.MAX_VALUE` | **Error** | Succeeds |
| `Long.MAX_VALUE + 1` | **Error** | **Error** |
| `Long.MIN_VALUE` | **Error** | Succeeds |
| `Long.MIN_VALUE - 1` | **Error** | **Error** |
| `2^64`, `2^100+123` | **Error** | **Error** |

Then test the bit-truncation behavior of **`intValue()`/`longValue()`** according to your policy. Do not claim it is "close" to the original value; conversion is modulo bit-width, not nearest-value approximation.

For unsigned protocol data, add tests for **positive/negative signed fields** and **unsigned bit-pattern fields**, e.g., `2^32-1` or `2^64-1`. Ensure sending and receiving layers agree on bit width and sign interpretation.

## 23. Several Application Scenarios

### A. Counts or Sizes

An endpoint receives a `BigInteger` for a record count. Calling `intValue()` on `2^32` gives 0, which could trick the program into thinking there are no records to process. When requiring a non-negative count fitting in signed `int`:

```java
static int validCount(BigInteger number) {
    if (number.signum() < 0) {
        throw new IllegalArgumentException("negative count");
    }
    return number.intValueExact();
}
```

**Two checks** carry two responsibilities: `signum() >= 0` for count semantics; `intValueExact()` for storage capability in the target type.

### B. IDs and Long-Length Integers

If IDs exceed signed 64 bits, narrowing with `longValue()` can cause two **distinct** IDs to share the same low 64 bits, creating collisions after conversion. If IDs must be unique, never truncate bits; keep **`BigInteger`** or use `String`/a sufficiently wide database type by design. When an API strictly allows only `long`, use `longValueExact()` to reject unsuitable values.

### C. Encoding an Unsigned 32-Bit Field

A protocol specifies a 32-bit unsigned field. The value `4294967295` is valid, yet `intValueExact()` cannot represent it as a positive signed `int`. You can deliberately create the 32-bit pattern with `intValue()` **after checking the unsigned range**, and read/write using unsigned APIs. This conversion differs from exact signed-integer conversion.

### D. Multi-Step Calculations

If computing a product that may exceed `long`:

```java
BigInteger result = BigInteger.valueOf(Long.MAX_VALUE)
        .multiply(BigInteger.valueOf(2));
// Keep BigInteger throughout the entire calculation chain.
```

**Defer narrowing** until the boundary that genuinely requires a primitive, then choose `longValueExact()` if data loss is unacceptable. Converting early to `longValue()` can destroy exact results that `BigInteger` preserved.

## 24. Common Misconceptions

| Misconception | Reality | Right approach |
| --- | --- | --- |
| `intValue()` checks for out-of-range automatically | It only takes **low 32 bits**, never throws overflow | Use `intValueExact()` when preservation is needed |
| `longValue()` is big enough for every `BigInteger` | `long` is only 64-bit signed | Use `longValueExact()` or keep `BigInteger` |
| Truncating large numbers gives `Integer.MAX_VALUE` | No saturation; can return negative/0 | Write a separate clamp policy if needed |
| `2^32` converted to `int` stays a large positive number | Low 32 bits are 0 | Use `long`/`BigInteger` |
| `2^64` converted to `long` yields `2^64` | Low 64 bits are 0 | `longValueExact()` throws |
| `intValueExact()` checks for non-negative numbers | It checks only signed range | Combine with `signum()` for non-negative domain |
| Only positive numbers wrap around | Out-of-range negative numbers also turn positive or 0 | Test both signed boundaries |
| `Math.toIntExact(big.longValue())` is always safe enough | `longValue()` may already have dropped bits | Call `big.intValueExact()` directly |
| `intValue()` returning 123 means `BigInteger` equals 123 | Could be `2^100+123` | Distinguish original value from low bits |
| `intValueExact()` validates input digit count/format | It checks value only | Validate input `String` separately |
| `longValueExact()` works for unsigned `2^64-1` | Signed `long` cannot hold that value | Validate unsigned and use bit-pattern convention |
| Converting to `double` then casting to `int`/`long` is more accurate | `double` has rounding error and limits | Avoid floating-point for exact integers |
| Catch `ArithmeticException` and call `intValue()` | Silently ignores critical error | Return meaningful error or change target type |

## 25. Knowledge Self-Check

1. **What is the short difference between `intValue()` and `intValueExact()`?** The regular one keeps low 32 bits and may lose data; the exact one rejects numbers outside signed `int` with `ArithmeticException`.
2. **What does `BigInteger("4294967296").intValue()` return?** 0, because `2^32` has all low 32 bits equal to 0.
3. **For that same `BigInteger` `2^32`, does `longValueExact()` succeed?** Yes, returning `4294967296L` because it fits in signed `long`.
4. **What does `BigInteger.valueOf(Integer.MAX_VALUE).add(BigInteger.ONE).intValue()` return?** `Integer.MIN_VALUE`, i.e. `-2147483648`.
5. **What does `BigInteger.valueOf(Integer.MIN_VALUE).subtract(BigInteger.ONE).intValue()` return?** `Integer.MAX_VALUE`, i.e. `2147483647`.
6. **What does `BigInteger.ONE.shiftLeft(64).longValue()` return?** 0, because `2^64` has all low 64 bits equal to 0.
7. **What happens with `BigInteger.ONE.shiftLeft(64).longValueExact()`?** Throws `ArithmeticException` because `2^64` exceeds signed `long`.
8. **What does `BigInteger("18446744073709551615").longValue()` give?** -1, because all low 64 bits are 1.
9. **Does `longValueExact()` throw an error on `Long.MIN_VALUE`?** No. That is the valid lower bound of signed `long`.
10. **Can `intValueExact()` be used to check whether a value lies in `0..2^32-1`?** No; it checks only signed `int`. Unsigned requires a separate range validator.
11. **Does an enormous number with `intValue() == 123` mean it equals 123?** No. `2^100+123` also returns 123 when keeping only low 32 bits.
12. **Is `Math.toIntExact(big.longValue())` always safe for `BigInteger`?** No; the `longValue()` step can lose data before `Math.toIntExact` ever sees the result.
13. **To reduce data loss risk when passing `BigInteger` to an API accepting `long`, what should be used?** `longValueExact()`; on error, handle it or change the design to keep `BigInteger`.
14. **Does `Exact` guarantee only range or also business rules?** It only guarantees the numeric value fits within the target type's signed range. Non-negativity, quotas, and input syntax must be validated separately.

**Key takeaway:** For `BigInteger`, **`intValue()` and `longValue()` extract low-order bits**; if the number exceeds range, results can change dramatically **without any exception**. Conversely, **`intValueExact()` and `longValueExact()` require exact representation of the entire value in signed 32/64 bits**, otherwise **throwing `ArithmeticException`**. When values of large integers must be preserved in real systems, prefer the `Exact` APIs, check business ranges, and truncate bits intentionally only when the data contract itself demands it.