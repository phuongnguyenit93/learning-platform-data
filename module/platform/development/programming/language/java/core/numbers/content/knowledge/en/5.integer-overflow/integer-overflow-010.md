# Using `BigInteger` When Value Ranges Have No Suitable Fixed Limit

> **Java core – numbers · Overflow and Boundary Checks**  
> Goal: recognize when `int`/`long` cannot cover the data range, switch to `BigInteger` before overflowing, perform exact integer arithmetic, convert safely, and control memory/performance risks.

## 1. When Is `long` Not Enough?

Java's primitive integer types have **fixed value ranges**:

| Type | Signed Range | Width |
| --- | --- | --- |
| `byte` | −128 to 127 | 8 bits |
| `short` | −32,768 to 32,767 | 16 bits |
| `int` | −2,147,483,648 to 2,147,483,647 | 32 bits |
| `long` | −9,223,372,036,854,775,808 to 9,223,372,036,854,775,807 | 64 bits |

When computing sums, products, or powers beyond limits, ordinary `int`/`long` integer arithmetic does not automatically expand its bit count. Results can **overflow** and wrap around under two's complement representation.

Example:

```java
long max = Long.MAX_VALUE;
long overflowed = max + 1;
System.out.println(overflowed); // -9223372036854775808
```

The desired mathematical result is **9,223,372,036,854,775,808**, yet this value is greater than `Long.MAX_VALUE`. If the business requirement must preserve that exact number, `long` is no longer suitable.

**`java.math.BigInteger` is the choice for storing and computing exact integers beyond primitive ranges.** "Arbitrary precision" means the bit count can grow with the number's magnitude instead of being locked at 32 or 64 bits. That **does not mean unlimited resources**: memory capacity, processing time, and implementation limits remain finite.

## 2. Do Not Wait for Overflow Before Switching to `BigInteger`

The most common mistake is computing in `long` first and then trying to "rescue" it by creating a `BigInteger`:

```java
long a = Long.MAX_VALUE;
long bad = a + 1;                      // already overflowed
BigInteger tooLate = BigInteger.valueOf(bad); // keeps the already-wrong negative value
```

You must **convert before the operation that risks overflowing**:

```java
import java.math.BigInteger;

long a = Long.MAX_VALUE;
BigInteger correct = BigInteger.valueOf(a).add(BigInteger.ONE);
System.out.println(correct); // 9223372036854775808
```

For multiplication, the rule is identical:

```java
long x = 5_000_000_000L;
long y = 5_000_000_000L;

// long bad = x * y; // would overflow long
BigInteger product = BigInteger.valueOf(x)
        .multiply(BigInteger.valueOf(y));
// product = 25000000000000000000
```

Avoid `new BigInteger(String.valueOf(x * y))`: the `x * y` part already ran in `long` and could overflow. Convert the **operands** first, not the **already-corrupted result**.

If the requirement is "keep using primitives while knowing when overflow occurs," use `Math.addExact`, `Math.subtractExact`, `Math.multiplyExact`, and `Math.negateExact` on `int`/`long`; these methods throw `ArithmeticException` when the operation does not fit in the target type. They **detect overflow** rather than adding bit width.

## 3. Choosing `BigInteger` Based on Value Range and Business Requirements

Situations where `BigInteger` is commonly warranted:

- **Counters, transaction volumes, or combinatoric counts** whose growth range `long` cannot safely guarantee.
- **Factorials, combinations, integer powers**: values grow very rapidly even when inputs are small.
- **Integer-arithmetic algorithms** needing integer quotients, GCD, remainders, modular exponentiation, or large integers.
- **Integer values from external systems** longer than 64 bits where every digit must be preserved verbatim.
- **Open-ended value-range problems**: no usable upper bound exists yet, or business limits are insufficient to guarantee `long` safety.

You should not replace every `int` and `long` with `BigInteger` out of habit. An array index, small sequence number, timestamp in a known range, or counter guaranteed not to exceed `long` is usually better suited to primitives. Conversely, **do not pick a type from current sample values**: consider the largest value that can appear during real system operation.

**Example from factorials:**

```text
20! = 2432902008176640000    (still fits in long)
21! = 51090942171709440000   (exceeds Long.MAX_VALUE)
```

This is clear evidence that `long` is unsuitable if a program needs to compute factorials for `n >= 21` and keep exact results. Choose `BigInteger` right from the start of the loop:

```java
BigInteger result = BigInteger.ONE;
for (int i = 2; i <= 21; i++) {
    result = result.multiply(BigInteger.valueOf(i));
}
System.out.println(result); // 51090942171709440000
```

Note that `BigInteger` does not automatically prevent a program from receiving huge inputs such as millions of digits or gigantic exponents. Alongside choosing the right type, you still need **input limits** and **resource budgets**.

## 4. Initializing `BigInteger` Properly

`BigInteger` belongs to the `java.math` package and is an *immutable* class extending `Number`. It has no dedicated literal syntax like `123L`.

### 4.1. From an in-range `long`

```java
BigInteger small = BigInteger.valueOf(123L);
BigInteger negative = BigInteger.valueOf(-45L);
BigInteger zero = BigInteger.ZERO;
BigInteger one = BigInteger.ONE;
BigInteger ten = BigInteger.TEN;
```

Java 17+ also provides `BigInteger.TWO`. Use these standard constants when appropriate to avoid unnecessary object creation.

### 4.2. From a decimal or other radix string

When a value exceeds the `long` range, the straightforward approach is passing **the full string of digits**:

```java
BigInteger huge = new BigInteger("9223372036854775808");
BigInteger belowZero = new BigInteger("-999999999999999999999");
BigInteger hex = new BigInteger("FF", 16); // 255
BigInteger binary = new BigInteger("1010", 2); // 10
```

The `new BigInteger(String, radix)` constructor accepts bases from 2 to 36. Do **not** pass a `0x` prefix when parsing a base-16 string this way:

```java
BigInteger hex = new BigInteger("FF", 16);   // correct
// new BigInteger("0xFF", 16);               // NumberFormatException
```

Invalid strings throw `NumberFormatException`; user-supplied data must be validated and length-bounded before parsing.

### 4.3. Mistake: using an out-of-range `long` literal

```java
// Does not compile: this integer literal does not fit in long
// BigInteger bad = BigInteger.valueOf(9223372036854775808L);

BigInteger good = new BigInteger("9223372036854775808");
```

The `_` separator is allowed in **Java source numeric literals**, but is not recognized as a separator inside decimal strings passed to `new BigInteger("...")`.

## 5. `BigInteger` Is Immutable: Methods Return a New Object

Unlike primitives with `+`, `-`, `*`, and `/` operators, standard operations on `BigInteger` are invoked via **methods**:

| Need | `BigInteger` Method |
| --- | --- |
| Add | `a.add(b)` |
| Subtract | `a.subtract(b)` |
| Multiply | `a.multiply(b)` |
| Integer quotient division | `a.divide(b)` |
| Quotient and remainder | `a.divideAndRemainder(b)` |
| Remainder per integer division | `a.remainder(b)` |
| Modulo with positive modulus | `a.mod(m)` |
| Negate | `a.negate()` |
| Absolute value | `a.abs()` |
| Integer exponentiation | `a.pow(exponent)` |
| Greatest common divisor | `a.gcd(b)` |
| Left/right bit shift | `a.shiftLeft(n)`, `a.shiftRight(n)` |

Because an object **cannot be modified in place** after creation, you must capture the return value:

```java
BigInteger count = BigInteger.TEN;
count.add(BigInteger.ONE);         // returns 11, but it is discarded
System.out.println(count);       // 10

count = count.add(BigInteger.ONE);
System.out.println(count);       // 11
```

You cannot write `count++` or `count += BigInteger.ONE`: Java does not overload arithmetic operators for `BigInteger`. Across consecutive calculations, the code must store the result explicitly.

## 6. Division and Remainder: Pay Special Attention to Negative Numbers

`BigInteger.divide()` returns an **integer quotient truncated toward 0**, just like Java's primitive integer division. If the divisor is 0, `ArithmeticException` is thrown.

```java
BigInteger a = BigInteger.valueOf(-17);
BigInteger b = BigInteger.valueOf(5);

System.out.println(a.divide(b));    // -3
System.out.println(a.remainder(b)); // -2
System.out.println(a.mod(b));       // 3
```

Difference between `remainder` and `mod`:

- `a.remainder(b)` gives the remainder from division truncating toward 0; a non-zero remainder has the **same sign as the dividend**.
- `a.mod(m)` requires a **positive modulus** and returns a **non-negative** remainder from 0 to `m - 1`.
- Use `divideAndRemainder(b)` when you need both quotient and remainder in a single calculation.

```java
BigInteger[] qr = a.divideAndRemainder(b);
System.out.println(qr[0]); // -3
System.out.println(qr[1]); // -2
```

Choose the remainder rule matching your problem. For circular index buffers or modular arithmetic, `mod(positiveModulus)` is usually more sensible than `remainder` when inputs can be negative.

## 7. Comparison, Sign, and Exact Conversions

### 7.1. Do not use primitive comparison operators on `BigInteger`

```java
BigInteger a = new BigInteger("100000000000000000000");
BigInteger b = new BigInteger("99999999999999999999");

System.out.println(a.compareTo(b) > 0); // true
System.out.println(a.equals(b));        // false
```

`compareTo` returns a negative value, 0, or a positive value depending on whether `a < b`, `a == b`, or `a > b`. `equals` compares the integer values of two `BigInteger`s; unlike `BigDecimal`, `BigInteger` **has no scale** affecting `equals`.

- `signum()`: returns `-1`, `0`, or `1` corresponding to negative, zero, or positive.
- `min` and `max`: pick the smaller/larger value by ordering.
- `bitLength()`: helps estimate binary magnitude; this is not the number of decimal digits.

If a reference can be `null`, handle `null` before calling methods.

### 7.2. Distinguish lossy conversions from exact conversions

Methods inherited from `Number`, such as `intValue()` and `longValue()`, **do not guarantee value preservation** if the value is out of range. When converting to `long`, high bits may be lost.

```java
BigInteger overLong = new BigInteger("9223372036854775808");
System.out.println(overLong.longValue()); // -9223372036854775808

// long bad = overLong.longValueExact(); // throws ArithmeticException
```

If data must be exact, prefer `intValueExact()`, `longValueExact()`, `shortValueExact()`, and `byteValueExact()`. They throw `ArithmeticException` if the value cannot be represented accurately in the target type.

Checks should happen at **API boundaries**: converting a `BigInteger` to an external database/JSON/SDK type, returning a result to a module using `long`, or writing to a bit-bounded protocol. Data that is accurate inside `BigInteger` can still become wrong after converting to a narrow type.

## 8. Large-Number Calculations: Combinatorics and Exponentiation

`BigInteger` is useful when the digit count of results grows rapidly.

### 8.1. Integer exponentiation

```java
BigInteger power = BigInteger.TWO.pow(100);
System.out.println(power);
// 1267650600228229401496703205376
```

`pow(exponent)` accepts a non-negative `int` exponent. It produces an **exact integer** if it completes successfully, though it can consume a lot of memory for large exponents. `BigInteger` instances do not represent fractional parts: `divide` is integer division, not exact division for an arbitrary rational number.

### 8.2. Combinatorial counting

The formula `n!` grows fast. For systems needing `n!`, `C(n,k)`, or combinatorial counts, intermediate multiplications can also exceed `long`.

Example of computing `C(n,k)` without creating three huge factorials:

```java
import java.math.BigInteger;

public static BigInteger choose(int n, int k) {
    if (n < 0 || k < 0 || k > n) {
        throw new IllegalArgumentException("Require 0 <= k <= n");
    }

    k = Math.min(k, n - k);
    BigInteger result = BigInteger.ONE;
    for (int i = 1; i <= k; i++) {
        // Each step divides evenly by property of binomial coefficients.
        result = result.multiply(BigInteger.valueOf((long) n - k + i))
                       .divide(BigInteger.valueOf(i));
    }
    return result;
}
```

This is an **illustrative method** that must be placed inside a Java class to run; it is not a complete program. Using `long` in `(long) n - k + i` prevents the factor calculation from overflowing `int` at boundary values. Each step stays an integer because the accumulated combinatorial product is evenly divisible by `i`.

## 9. Check Overflow First or Use `BigInteger` from the Start?

Different systems set different requirements:

| Requirement | Solution Approach |
| --- | --- |
| Range known to stay inside `int`/`long` | Use primitives, validate inputs if needed |
| Must stay primitive yet block out-of-range operations | Use `Math.*Exact`; handle `ArithmeticException` |
| Operation may exceed `long`, result must be exact integer | Convert operands to `BigInteger` **before** the operation |
| Large result, but output port accepts only `long` | Keep `BigInteger` in the core, check bounds / `longValueExact()` at the output port |
| Data has fractional parts and needs business rounding rules | Use `BigDecimal`, not `BigInteger` directly |

Example of an addition requiring **an error** when exceeding `long`:

```java
long total = Math.addExact(current, incoming);
```

If the same addition requires **preserving the exact result even beyond `long`**:

```java
BigInteger total = BigInteger.valueOf(current)
        .add(BigInteger.valueOf(incoming));
```

Choose according to the **data contract**. Do not swallow exceptions from `Math.addExact` and silently record a wrapped-around value; likewise, do not arbitrarily return a `BigInteger` string to an API requiring a 64-bit type without defining the value-exchange contract.

## 10. `BigInteger` and Signed/Unsigned Binary Representation

`BigInteger` is a **signed** integer. You can parse very large positive decimal strings, yet when reading a **byte array**, sign interpretation must be chosen explicitly.

Example with two bytes `FF 00`:

```java
byte[] bytes = {(byte) 0xFF, 0x00};

BigInteger signed = new BigInteger(bytes);
BigInteger unsigned = new BigInteger(1, bytes);

System.out.println(signed);   // -256
System.out.println(unsigned); // 65280
```

The `new BigInteger(byte[])` constructor treats the bytes as two's complement in *big-endian* byte order. The `new BigInteger(signum, magnitude)` constructor uses a separate sign and an unsigned magnitude. **Do not assume every `byte[]` is positive** if the highest byte has sign bit 1.

When exporting bytes with `toByteArray()`, the output is big-endian two's complement with enough bytes to preserve the sign; a positive number whose highest bit is 1 may need a leading `00` byte. If a protocol requires fixed byte length or unsigned encoding, verify length, sign, and padding before writing.

For a 64-bit pattern meant to be interpreted as an **unsigned long**:

```java
long bits = -1L; // all 64 bits are 1
BigInteger unsigned64 =
        new BigInteger(Long.toUnsignedString(bits));
System.out.println(unsigned64); // 18446744073709551615
```

`BigInteger.valueOf(bits)` would be `-1` because it preserves the **signed long value**, without converting to unsigned. Use `Long.toUnsignedString` (or verified bit-level conversion) when the source specification defines 64-bit unsigned values.

## 11. Memory, Performance, and Safety Limits

Every `BigInteger` is an object holding the data for the integer's magnitude. The more bits a number has, the more time and memory operations consume. Multiplying huge numbers, `pow` with large exponents, converting to decimal strings, or parsing millions of digits can consume heavy resources.

**Practical principles:**

1. Limit input string length, exponent range, loop counts, and result digit counts **according to product requirements**.
2. If many-digit integers are needed on a real-time processing path, benchmark with realistic data sizes.
3. Avoid building gigantic result strings just for logging; cap logs and inspect only necessary details.
4. For large-scale calculations, specify time and memory requirements explicitly; do not assume `BigInteger` guarantees completion for every value.
5. Do not use `BigInteger` as a solution for problems needing **real/decimal numbers**: `divide` is still integer division. For money and exact decimals needing scale/rounding, choose `BigDecimal`.

Do not apply "`BigInteger` is always better because it doesn't overflow" to every case. It **preserves exact integer values** when ranges are large, while still requiring explicit cost bounds in the design.

## 12. Standalone Runnable Java 17+ Program

Create the file **`BigIntegerOverflowDemo.java`**:

```java
import java.math.BigInteger;

public class BigIntegerOverflowDemo {
    public static void main(String[] args) {
        long max = Long.MAX_VALUE;
        System.out.println("long overflow = " + (max + 1));

        BigInteger safe = BigInteger.valueOf(max).add(BigInteger.ONE);
        System.out.println("long max + 1 = " + safe);

        BigInteger factorial = BigInteger.ONE;
        for (int i = 2; i <= 21; i++) {
            factorial = factorial.multiply(BigInteger.valueOf(i));
        }
        System.out.println("21! = " + factorial);
        System.out.println("21! exceeds long = "
                + (factorial.compareTo(BigInteger.valueOf(max)) > 0));

        try {
            factorial.longValueExact();
            System.out.println("21! fits long");
        } catch (ArithmeticException ex) {
            System.out.println("21! cannot fit in long");
        }

        BigInteger a = BigInteger.valueOf(-17);
        BigInteger b = BigInteger.valueOf(5);
        System.out.println("-17 / 5 = " + a.divide(b));
        System.out.println("-17 remainder 5 = " + a.remainder(b));
        System.out.println("-17 mod 5 = " + a.mod(b));

        byte[] bytes = {(byte) 0xFF, 0x00};
        System.out.println("FF00 signed = " + new BigInteger(bytes));
        System.out.println("FF00 unsigned = " + new BigInteger(1, bytes));

        BigInteger original = BigInteger.TEN;
        BigInteger changed = original.add(BigInteger.ONE);
        System.out.println("immutable: " + original + ", " + changed);
    }
}
```

Compile and run in the directory containing the file:

```bash
javac BigIntegerOverflowDemo.java
java BigIntegerOverflowDemo
```

**Expected output:**

```text
long overflow = -9223372036854775808
long max + 1 = 9223372036854775808
21! = 51090942171709440000
21! exceeds long = true
21! cannot fit in long
-17 / 5 = -3
-17 remainder 5 = -2
-17 mod 5 = 3
FF00 signed = -256
FF00 unsigned = 65280
immutable: 10, 11
```

The program highlights the differences between **primitive overflow** and **exact integer arithmetic**, between **lossy conversion** and **exact conversion**, between **`remainder`** and **`mod`**, as well as byte signedness and `BigInteger` immutability.

## 13. Common Mistakes

| Mistake | Consequence | Correct Approach |
| --- | --- | --- |
| Computing `long * long` then wrapping in `BigInteger` | The product may have overflowed before wrapping | Convert operands with `valueOf` before `multiply` |
| Writing a number exceeding `long` as a literal with `L` suffix | Does not compile | Use `new BigInteger("...")` |
| Writing `value + BigInteger.ONE` | No `+` operator overload for `BigInteger` | Use `value.add(BigInteger.ONE)` |
| Calling `count.add(ONE)` without assigning | The original object is unchanged | `count = count.add(ONE)` |
| Using `longValue()` when exactness is required | Can lose high bits and produce an unintended negative number | Use `longValueExact()` |
| Using `==` to compare two `BigInteger`s | Compares references, not values | Use `equals` or `compareTo` |
| Thinking `divide` keeps fractional parts | Integer quotient truncates the fraction | Use `BigDecimal` if decimals are truly needed |
| Thinking `remainder` is always non-negative | With a negative dividend, the remainder can be negative | Specify clearly whether `remainder` or `mod` is needed |
| Reading bytes with high bit 1 assuming unsigned | Value can turn negative | Determine signedness, use the matching constructor |
| Believing arbitrary precision means unlimited resources | Can run out of memory, burn CPU | Bound input/exponent/output per system limits |

## 14. Exercises and Solutions

**Exercise 1.** Why is `BigInteger.valueOf(Long.MAX_VALUE + 1)` **not** the right way to compute `Long.MAX_VALUE + 1`?  
**Solution:** the addition runs in `long` and already overflowed to `Long.MIN_VALUE`. Right way: `BigInteger.valueOf(Long.MAX_VALUE).add(BigInteger.ONE)`.

**Exercise 2.** Do factorials `20!` and `21!` fit in `long`?  
**Solution:** `20! = 2432902008176640000` still fits; `21! = 51090942171709440000` exceeds `Long.MAX_VALUE`. Choose `BigInteger` if exact `21!` is needed.

**Exercise 3.** What does `new BigInteger("9223372036854775808").longValueExact()` do?  
**Solution:** throws `ArithmeticException` because the number is larger than the positive range of `long`. Calling `longValue()` instead would return a negative value contrary to intent, so `Exact` is appropriate when the contract requires preserving the exact number.

**Exercise 4.** With `a = -17` and `b = 5`, what are `a.remainder(b)` and `a.mod(b)`?  
**Solution:** **−2** and **3** respectively; `mod` requires a positive modulus and yields a non-negative result.

**Exercise 5.** Can `BigInteger` replace `BigDecimal` to add `0.10 + 0.20` directly and accurately?  
**Solution:** not directly as decimals; `BigInteger` represents **integers**. You could convert to the smallest integer unit if the business has a fixed scale, yet when decimal operations with scale and rounding are needed, using `BigDecimal` is usually clearer.

**Exercise 6.** What values do the two bytes `FF 00` yield when read via `new BigInteger(bytes)` and `new BigInteger(1, bytes)`?  
**Solution:** **−256** and **65280** respectively; the first constructor uses signed two's complement, while the second sets a positive sign and interprets an unsigned magnitude.

**Exercise 7.** A system stores product quantities up to 1 million and performs no overflowing multiplications. Is `BigInteger` needed?  
**Solution:** usually not; `int` has a large enough range. Correctness also depends on intermediate operations and data constraints, so check sums/products if the business logic uses them.

## 15. Checklist Before Choosing `BigInteger`

1. **Value range:** are there reliable lower/upper bounds, or could values exceed `long`?
2. **Intermediate operations:** even if inputs fit in `long`, could products, factorials, or multi-value sums cross the threshold?
3. **Error requirement:** do you need to report overflow via `Math.*Exact`, or continue computing with exact large integers?
4. **Input source:** is it a valid `long`, a very long digit string, or a byte array needing explicit signedness?
5. **Output port:** can large values be stored/exported as-is, or must they convert back to `int`/`long`? If converting, will `*ValueExact()` be used?
6. **Division semantics:** do you need an integer quotient, remainder, modulo, or exact decimal numbers?
7. **Cost:** have limits on input length, exponents, loop counts, and result size been established?

**Remember:** When `int`/`long` do not have enough range yet **exact integers** are still required, move operands into `BigInteger` **before the operation**, use methods instead of arithmetic operators, capture return values because objects are immutable, and check bounds when converting back to finite types. "Arbitrary precision" solves the **bit-width limit** problem, while still requiring **resource-limit** management.
