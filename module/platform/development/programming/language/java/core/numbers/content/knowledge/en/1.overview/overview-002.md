# Distinguishing Mathematical Value, Data Type, and Storage Representation in Java

In numeric programming, three concepts are often conflated: **mathematical value** (the number we want to describe), **data type** (the values and operations the program allows), and **representation/storage** (the bits or data structures the computer uses to encode the value). Separating these three layers helps explain why `0.1 + 0.2` does not produce exact `0.3`, why `int` overflows, and why two numbers that look the same still behave differently in Java.

## 1. Three Layers to Distinguish

| Layer | Question to Answer | Example |
| --- | --- | --- |
| Mathematical value | What quantity are we talking about, independent of the computer? | Integer 42; fraction 1/3; real number 0.1; negative −5 |
| Data type | What value range and operations does Java allow? | `int`, `long`, `double`, `BigInteger`, `BigDecimal` |
| Representation/storage | How is the value encoded and is it exact? | `int` has 32-bit two's complement; `double` uses binary floating-point; `BigDecimal` uses unscaled integer and scale |

For example, **42** is a mathematical value. The following declarations can carry the same arithmetic value 42 while having different types/representations:

```java
int a = 42;
long b = 42L;
double c = 42.0;
BigInteger d = new BigInteger("42");
BigDecimal e = new BigDecimal("42.00");
```

`a` and `b` are exact integers within a finite range, `c` is a binary floating-point number (42 is a small integer that can be represented exactly), `d` is an integer of arbitrary magnitude within resource limits, while `e` represents an exact decimal with **unscaled value = 4200**, **scale = 2**. In `BigDecimal`, `42.00` and `42.0` are equal in **numeric value** but differ in **scale**, which affects `equals()`.

> Note: how a number is **displayed** with characters (`"42"`, `"42.00"`) is yet another layer. A text string is not automatically a numeric-type value.

## 2. Value Range and Encoding of Primitive Integers

Java specifies the size and value range for signed integer types:

| Type | Logical Width | Value Range (Inclusive) |
| --- | ---: | --- |
| `byte` | 8 bits | −128 to 127 |
| `short` | 16 bits | −32,768 to 32,767 |
| `int` | 32 bits | −2,147,483,648 to 2,147,483,647 |
| `long` | 64 bits | −9,223,372,036,854,775,808 to 9,223,372,036,854,775,807 |

For a signed integer type of `n` bits, the range is `−2^(n−1)` to `2^(n−1)−1`, because there are finitely many `2^n` bit patterns. Java uses **two's complement** to represent signed integers. For example, in 8 bits: `0000_0101` represents +5, while `1111_1011` represents −5. The same sequence of bits only has numeric meaning after attaching an **interpretation rule and width**.

`char` is a 16-bit **unsigned** integral type with range `0` to `65535`, used for UTF-16 code units. `char` is not a type meant for general numeric calculation, and one Unicode character can require two `char`s. Java has no independent unsigned primitive integer types like C's `unsigned int`; methods like `Integer.toUnsignedLong` and `Integer.divideUnsigned` only **interpret operations** on `int` bit patterns in an unsigned sense.

### Overflow Does Not Change the Mathematical Value, It Changes the Represented Result

```java
int max = Integer.MAX_VALUE;
System.out.println(max + 1);             // -2147483648
System.out.println(Math.addExact(max, 1)); // throws ArithmeticException
```

The mathematical value `2_147_483_647 + 1` is `2_147_483_648`, but the ordinary `int` result wraps around to the smallest value because integer arithmetic only keeps 32 bits of the result. Java **does not automatically throw an exception** for `+`, `-`, `*` integer overflow. Use `Math.addExact`, `subtractExact`, `multiplyExact`, or convert to `long`/`BigInteger` before the operation when overflow control is needed.

Watch out: casting **after an `int` multiplication has already overflowed** cannot recover the right result:

```java
int x = 1_000_000_000;
long wrong = (long) (x * 3); // -1294967296: int multiplication first
long right = (long) x * 3;   // 3000000000: long multiplication
```

When narrowing from `int` to `byte`, Java keeps only the low 8 bits; `(byte) 130` yields `-126`, not a mathematical value 130 that could fit in `byte`. Conversely, assigning `byte b = 130;` is a compile error because the integer constant does not fit in the target type.

## 3. Floating-Point Types Are Binary Approximations with Their Own Rules

`float` (32 bits) and `double` (64 bits) use IEEE 754 **binary32/binary64** format, with sign bit, exponent, and *significand*. Precision is finite: about **7 significant decimal digits** for `float` and **15–16 digits** for `double`; this is a usage estimate, not a fixed number of digits after the decimal point.

Many decimal fractions such as `0.1` cannot be written finitely in base 2. Java stores the nearest binary number, so:

```java
System.out.println(0.1 + 0.2);       // 0.30000000000000004
System.out.println(0.1 + 0.2 == 0.3); // false
System.out.println(0.5 + 0.25);      // 0.75
```

`0.5 = 1/2` and `0.25 = 1/4` have finite binary representations so they are exact here; `0.1` and `0.2` do not. **Printing `0.1` does not mean the bits in `double` store the exact mathematical fraction 1/10**: `Double.toString` picks a short decimal string that parses back to the same `double` value.

Do not test approximate equality with `==` when rounding error can occur. For measurements with error, consider absolute/relative tolerance based on the problem domain, such as:

```java
static boolean nearlyEqual(double a, double b, double absTol, double relTol) {
    if (Double.doubleToLongBits(a) == Double.doubleToLongBits(b)) return true;
    if (!Double.isFinite(a) || !Double.isFinite(b)) return false;
    double diff = Math.abs(a - b);
    return diff <= Math.max(absTol, relTol * Math.max(Math.abs(a), Math.abs(b)));
}
```

This function is a **comparison policy for cases with tolerance**, not a definition of equality for every problem. Choose `absTol` and `relTol` from measurement requirements, not a single fixed epsilon for all magnitudes. If exact monetary/decimal values are required, prefer `BigDecimal`.

### Special Floating-Point Cases

- `Double.POSITIVE_INFINITY`/`NEGATIVE_INFINITY` can appear due to floating-point magnitude overflow, or dividing a nonzero finite number by ±0.0; they are not finite real numbers.
- `Double.NaN` represents an undefined result under IEEE 754; `Double.NaN == Double.NaN` returns `false`. Check using `Double.isNaN(x)`.
- `+0.0` and `-0.0` compare equal with `==`, but their sign can affect operations such as `1.0 / -0.0` producing `-Infinity`.
- For `double`, every integer with absolute value **not exceeding `2^53`** is represented exactly, though not every integer above that threshold is. `double` can have a wider magnitude range than `long` while still losing unit detail.

## 4. `BigInteger` and `BigDecimal`: Precision Determined by the Data Model

### `BigInteger`: Exact Integers, Not Limited by 32/64 Bits

`BigInteger` holds integer values in a multi-word structure, can store numbers exceeding `Long.MAX_VALUE`, and uses methods `add`, `multiply`, `divide`, and `mod`. Practical magnitude is bounded by memory, performance, and implementation limits; objects are **immutable**.

```java
BigInteger beyondLong = BigInteger.valueOf(Long.MAX_VALUE)
        .add(BigInteger.ONE);
System.out.println(beyondLong); // 9223372036854775808
```

### `BigDecimal`: Decimal Numbers as `unscaledValue × 10^(−scale)`

The two core components are **an arbitrary integer** and **scale**, not a "pretty-printed" binary `double` value:

```java
BigDecimal amount = new BigDecimal("12.30");
System.out.println(amount.unscaledValue()); // 1230
System.out.println(amount.scale());         // 2
System.out.println(amount);                 // 12.30
```

Construct `BigDecimal` from a decimal string when the source is a string/monetary decimal:

```java
BigDecimal a = new BigDecimal("0.1");
BigDecimal b = new BigDecimal("0.2");
System.out.println(a.add(b)); // 0.3
```

**Avoid `new BigDecimal(0.1)` if you want to represent the exact decimal 0.1**: the constructor receives the rounded binary `double` value itself, so the result contains trailing approximate digits. `BigDecimal.valueOf(0.1)` goes through `double`'s canonical decimal representation and is usually more suitable, though if the original input is decimal text, keeping the original string remains clearest.

`BigDecimal` is exact for addition/subtraction/multiplication on already-represented finite decimals, but **division can produce an infinite expansion**: `BigDecimal.ONE.divide(new BigDecimal("3"))` throws `ArithmeticException` if no rounding policy is provided. Choose `scale`/`RoundingMode` or `MathContext`:

```java
BigDecimal oneThird = BigDecimal.ONE.divide(
        new BigDecimal("3"), 2, RoundingMode.HALF_UP);
System.out.println(oneThird); // 0.33
```

`BigDecimal.equals()` checks both value and scale: `new BigDecimal("1.0").equals(new BigDecimal("1.00"))` is `false`. `compareTo()` compares numeric value and returns `0` in this case. Stripping extra zeros with `stripTrailingZeros()` can change scale/representation; when used as keys in `HashMap`/`HashSet`, watch the `equals/hashCode` contract.

## 5. Literals, Operations, and Casts Can Change Results

### Writing Literals with the Right Type

| Expression | Default Type / Value | Notes |
| --- | --- | --- |
| `42` | `int` | Decimal integer constants default to `int` if they fit |
| `42L` | `long` | `L` should be uppercase, especially next to digit 1 |
| `42.0`, `1e3` | `double` | Floating-point constants default to `double` |
| `42.0f` | `float` | Suffix `f` or `F` |
| `0b101010`, `0x2A` | `int` with value 42 | Binary and hexadecimal are just literal notations |
| `1_000_000` | `int` with value 1,000,000 | Underscores are syntax only, not stored in the value |
| `"42"` | `String` | Text, not automatically a number |

Note that the literal `010` in Java is **octal** (value 8), not ten; putting a leading 0 on integer literals easily causes confusion. The `-` character in `-42` is the unary negation operator, not a "sign bit" in literal syntax.

### Operand Types Determine the Operation

```java
System.out.println(1 / 2);          // 0: integer division
System.out.println(1.0 / 2);        // 0.5: double division
System.out.println(5 / 2 * 2);      // 4: fractional part already lost after division
System.out.println((double) 5 / 2); // 2.5: converted before division
```

Operands of type `byte`, `short`, and `char` are normally **promoted** to `int` before arithmetic operations. For example, `byte a = 1, b = 2; byte c = a + b;` does not compile because `a + b` has type `int`, even though the mathematical value 3 fits in `byte`. Assigning to a narrower type requires a valid conversion or an explicit cast, accepting potential data loss.

Casting `double` to `int` **truncates the fractional part toward 0** when the value is within the allowed range; NaN converts to 0, and out-of-range values saturate to the respective boundary. Thus `(int) 3.9` is 3 and `(int) -3.9` is −3; this is not rounding to the nearest integer.

**Auto-boxing** (`int` ↔ `Integer`) changes using a primitive to a wrapper object; it does not widen the number's value range. With objects, `==` compares reference identity; use `equals` when comparing wrapper values, and watch out for `null` during unboxing.

## 6. Talking About "Storage" Without Confusing It with Memory Layout

- A primitive variable of type `int` describes a 32-bit value under Java's rules; `double` uses a 64-bit representation. This **does not mean** a guarantee that a variable always occupies exactly 4/8 bytes on the stack: stack frame layout, registers, alignment, and JIT optimizations are JVM implementation details.
- For `BigInteger`/`BigDecimal`, the reference variable points to an object holding the needed state; objects also carry overhead, may use internal arrays, and are managed by the JVM/GC. Total memory cannot be deduced solely from the digit count of the display string.
- Bit patterns, types, and display formatting must be kept separate: for example, the low bits `1111_1111` can be read as `255` if treated as an unsigned byte in a protocol, or `-1` if interpreted as Java `byte`. A character `'9'` has a Unicode code point different from the integer `9`.
- Conversions across JSON, CSV, databases, or network protocols must specify **number kind, value range, precision, units, and rounding rules**; a string `"9007199254740993"` can lose precision if passed intermediately through a `double`.

## 7. Standalone Java 17+ Example

Save to `NumericLayersDemo.java`:

```java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.RoundingMode;

public class NumericLayersDemo {
    public static void main(String[] args) {
        int integer = 42;
        double floating = 42.0;
        BigDecimal decimal = new BigDecimal("42.00");

        System.out.println("int: " + integer);
        System.out.println("double: " + floating);
        System.out.println("BigDecimal: " + decimal);
        System.out.println("0.1 + 0.2 = " + (0.1 + 0.2));
        System.out.println("1 / 2 = " + (1 / 2));
        System.out.println("1.0 / 2 = " + (1.0 / 2));
        System.out.println("int overflow = " + (Integer.MAX_VALUE + 1));
        System.out.println("decimal sum = "
                + new BigDecimal("0.1").add(new BigDecimal("0.2")));
        System.out.println("beyond long = "
                + BigInteger.valueOf(Long.MAX_VALUE).add(BigInteger.ONE));
        System.out.println("rounded third = "
                + BigDecimal.ONE.divide(new BigDecimal("3"), 2, RoundingMode.HALF_UP));
        System.out.println("same numeric value = "
                + (decimal.compareTo(new BigDecimal("42.0")) == 0));
    }
}
```

Compile and run in the directory containing the file:

```bash
javac NumericLayersDemo.java
java NumericLayersDemo
```

Output:

```text
int: 42
double: 42.0
BigDecimal: 42.00
0.1 + 0.2 = 0.30000000000000004
1 / 2 = 0
1.0 / 2 = 0.5
int overflow = -2147483648
decimal sum = 0.3
beyond long = 9223372036854775808
rounded third = 0.33
same numeric value = true
```

Each line illustrates the difference between **intended value**, **type calculation rules**, and **representational capability**. `double` represents `42` exactly but does not represent `0.1` exactly; `BigDecimal` preserves decimal 0.1 when constructed from a string; `int` cannot represent `MAX_VALUE+1`; `BigInteger` can.

## 8. Choosing a Type from Problem Requirements

| Need | Usually Suitable Choice | What to Check |
| --- | --- | --- |
| Counts, indices, quantities in a small range | `int` | Overflow during addition/multiplication, including intermediates |
| Integers larger than `int` range, timestamps/appropriate units | `long` | Still finite; check units and overflow |
| Arbitrarily large integers (cryptography, combinatorics, big numbers) | `BigInteger` | CPU/memory cost, immutable objects |
| Measurements/science, calculations tolerating floating-point error | `double`; sometimes `float` when resource-constrained | NaN, infinity, rounding, tolerance |
| Currency/specific decimal rules, decimal values needing exactness | `BigDecimal` or integer in smallest unit by contract | Scale, rounding, division, formatting, currency |
| Numeric data from external strings | Parse with range and format validation | Do not mistake display format for type; avoid going through `double` when exact decimal is required |

### Common Mistakes to Self-Check

1. **Confusing the displayed number with the stored number:** `System.out.println(0.1)` outputs "0.1" but `double` stores a binary approximation.
2. **Choosing a type by visible digit count:** `double` holds very large values but does not keep every 64-bit integer exact.
3. **Casting only at the result:** `(long) (a * b)` cannot rescue an `int` multiplication that has already overflowed.
4. **Assuming `BigDecimal` fixes bad input automatically:** constructing from `new BigDecimal(0.1)` already received the `double` approximation; keep the original decimal data.
5. **Forgetting that types govern operations:** `1 / 2` equals 0; `byte + byte` produces `int`.
6. **Confusing "exact" with infinite:** `BigDecimal` computes finite decimals exactly in many operations, yet dividing 1/3 requires specifying rounding; `BigInteger` is exact yet subject to resource limits.
7. **Asserting fixed stack/heap placement or object byte sizes:** logical sizes of primitives are defined by Java; physical memory layout is decided by the JVM.

## 9. Self-Check Your Understanding

- Why can `42`, `42.0`, and `new BigDecimal("42.00")` represent the same mathematical value while not sharing the same type, scale, and operations?
- With 32-bit `int`, why is `Integer.MAX_VALUE + 1` negative when the mathematical integer is non-negative?
- Why is `0.5` represented exactly in binary64 while `0.1` is not? When do you choose `double`, and when `BigDecimal`?
- Why does `BigDecimal("1.0").equals(BigDecimal("1.00"))` differ from `compareTo() == 0`? Why does this matter when used as keys?
- If the input string is `"9007199254740993"`, should you choose `long`, `double`, or `BigInteger` to preserve the exact value, and why?

**Application principle:** start from the **mathematical value range and precision requirements**, pick the **type and operations** that meet those requirements, then verify **representation, conversion, overflow, and display** at each data boundary.