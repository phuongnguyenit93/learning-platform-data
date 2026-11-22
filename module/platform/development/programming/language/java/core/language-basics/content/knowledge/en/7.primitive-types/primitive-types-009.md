# Value Limits with `MIN_VALUE`, `MAX_VALUE`, and `SIZE` — Java 17+

## 1. The Problem to Solve

Every Java primitive type has a defined **value range** or set of values. To choose a storage type, validate input, or prevent overflow, you need to know:

- **`MIN_VALUE`**: the lower bound as defined by the type (with a very important exception for floating-point numbers).
- **`MAX_VALUE`**: the largest finite value representable by that type.
- **`SIZE`**: the number of **bits** used to represent a value of the type, **not the number of bytes** and not the object size.

In Java, these constants live in the **wrapper classes** in `java.lang`: `Byte`, `Short`, `Integer`, `Long`, `Character`, `Float`, and `Double`. You can look them up without manually typing long numbers:

~~~java
System.out.println(Integer.MIN_VALUE); // -2147483648
System.out.println(Integer.MAX_VALUE); // 2147483647
System.out.println(Integer.SIZE);      // 32
~~~

**Key point:** not every type interprets `MIN_VALUE` the same way. In particular, `Float.MIN_VALUE` and `Double.MIN_VALUE` **are not the lowest negative values**.

## 2. Complete Table for the Four Signed Integer Types

| Primitive type | Wrapper | `MIN_VALUE` | `MAX_VALUE` | `SIZE` (bits) | `BYTES` |
|---|---|---:|---:|---:|---:|
| `byte` | `Byte` | -128 | 127 | 8 | 1 |
| `short` | `Short` | -32,768 | 32,767 | 16 | 2 |
| `int` | `Integer` | -2,147,483,648 | 2,147,483,647 | 32 | 4 |
| `long` | `Long` | -9,223,372,036,854,775,808 | 9,223,372,036,854,775,807 | 64 | 8 |

**`SIZE` measures bits; `BYTES` measures bytes in the value representation.** For example, `Integer.SIZE == 32` and `Integer.BYTES == 4`.

For a signed integer of width `n` bits using two's complement representation, the value range is:

\[
-2^{n-1} \;\leq x \leq\; 2^{n-1}-1.
\]

Thus an 8-bit `byte` ranges from \(-2^7=-128\) to \(2^7-1=127\). The negative range has one more value than the positive range. Therefore, `Integer.MIN_VALUE` cannot be negated into a positive number by `Math.abs` within the same `int` type.

### Example Looking Up Limits Without Memorizing Numbers

~~~java
int smallestInt = Integer.MIN_VALUE;
int largestInt = Integer.MAX_VALUE;
long smallestLong = Long.MIN_VALUE;
long largestLong = Long.MAX_VALUE;

System.out.println(smallestInt); // -2147483648
System.out.println(largestInt);  // 2147483647
System.out.println(Long.SIZE);   // 64
~~~

**Fixed limits across all Java platforms:** `int` is always a 32-bit value and `long` is always a 64-bit value by specification, regardless of Windows, Linux, OS, or 32/64-bit JVM.

## 3. `char`: 16 Bits, Yet Not a Signed Integer Type

`char` is a primitive type representing **one UTF-16 code unit**, not a signed `short`. Java provides:

| Constant | Value |
|---|---|
| `Character.MIN_VALUE` | U+0000 (numeric value 0) |
| `Character.MAX_VALUE` | U+FFFF (numeric value 65535) |
| `Character.SIZE` | 16 bits |
| `Character.BYTES` | 2 bytes |

~~~java
System.out.println((int) Character.MIN_VALUE); // 0
System.out.println((int) Character.MAX_VALUE); // 65535
System.out.println(Character.SIZE);           // 16
~~~

**Unicode note:** a `char` is a **UTF-16 code unit**; a Unicode character outside the BMP can require **two `char` values** (a surrogate pair). Thus `Character.SIZE == 16` does not mean Java only supports Unicode up to U+FFFF, nor does it mean every character the user sees occupies exactly one `char`.

`Character.MIN_VALUE` is the control character with code 0, not a character easily visible on screen. When you want to print the limits of `char`, **cast it to `int`** as in the example instead of trying to display the U+0000 character directly.

## 4. `float` and `double`: `MIN_VALUE` Means Something Different from Integers

This is the most important trap in the lesson.

| Constant | `float` | `double` |
|---|---:|---:|
| `SIZE` | 32 bits | 64 bits |
| `BYTES` | 4 bytes | 8 bytes |
| `MAX_VALUE` | `3.4028235E38` | `1.7976931348623157E308` |
| `MIN_VALUE` | `1.4E-45` | `4.9E-324` |
| `MIN_NORMAL` | `1.17549435E-38` | `2.2250738585072014E-308` |

**`Float.MIN_VALUE` and `Double.MIN_VALUE` are the smallest positive non-zero representable numbers**, in **subnormal** form. They are **not** `-Float.MAX_VALUE` or `-Double.MAX_VALUE`.

~~~java
System.out.println(Float.MIN_VALUE);  // 1.4E-45
System.out.println(Float.MAX_VALUE);  // 3.4028235E38
System.out.println(-Float.MAX_VALUE); // -3.4028235E38
~~~

If you need the **lowest finite number** in numerical order, use **`-Float.MAX_VALUE`** or **`-Double.MAX_VALUE`**.

### Why Does `MIN_NORMAL` Exist?

Binary floating-point numbers have a sign, exponent, and significand. Values very close to 0 can fall into the **subnormal** range, where effective precision is reduced to create small steps approaching 0. `MIN_NORMAL` is the smallest positive number in the normal range, while `MIN_VALUE` is the smallest positive non-zero subnormal number.

This pair of constants measures **value magnitude thresholds**, and does not guarantee a decimal calculation is exact. For example, `0.1 + 0.2` in `double` can differ from exact `0.3` due to binary precision limits.

### Infinity and NaN Still Exist

`MAX_VALUE` means the **largest finite value**, not that the value set of `double` only spans from `-Double.MAX_VALUE` to `Double.MAX_VALUE`. Floating-point types also have `Infinity`, `-Infinity`, and `NaN`.

~~~java
double tooLarge = Double.MAX_VALUE * 2;
System.out.println(tooLarge);           // Infinity
System.out.println(Double.isFinite(tooLarge)); // false
System.out.println(Double.isNaN(0.0 / 0.0));  // true
~~~

If a finite real number is required, **check `Double.isFinite(value)`** (or `Float.isFinite`) before using it. Checking only `value <= Double.MAX_VALUE` is not enough to determine valid data because of NaN and special comparison rules.

## 5. `boolean` Has No `MIN_VALUE`, `MAX_VALUE`, or `SIZE`

`boolean` only has **`true` and `false`**; the wrapper `Boolean` defines values such as `Boolean.TRUE` and `Boolean.FALSE`.

There is no standard API:

~~~java
// Boolean.MIN_VALUE // Does not exist
// Boolean.MAX_VALUE // Does not exist
// Boolean.SIZE      // Does not exist
~~~

The Java language does not expose a `Boolean.SIZE` constant analogous to `Integer.SIZE`. Do not deduce "a boolean always takes 1 bit of memory" from the fact that the type has only two states: how the JVM stores fields, local variables, arrays, headers, and alignment is an implementation detail distinct from the **abstract value domain** of `boolean`.

## 6. `SIZE` and `BYTES` Do Not Measure Object Size on the Heap

Example:

~~~java
System.out.println(Byte.SIZE);      // 8
System.out.println(Integer.SIZE);   // 32
System.out.println(Long.BYTES);     // 8
System.out.println(Double.BYTES);   // 8
~~~

These constants describe the **value representation width**, not the result of `sizeof` as in some other languages. Java has no `sizeof` operator for objects.

- A primitive variable has a fixed value width.
- An `Integer` instance can have object overhead, references, and its own alignment requirements.
- A `byte` field in an object does not necessarily increase the object size by exactly 1 byte, due to JVM memory layout.
- Arrays have overhead and layout beyond the bytes corresponding to each element.

When working with **binary buffers**, `Integer.BYTES` is useful for calculating the byte count of a 32-bit value. But to measure actual heap memory, use appropriate JVM profiling/measurement tools rather than multiplying `SIZE` to conclude total object footprint.

## 7. Use `MIN_VALUE`/`MAX_VALUE` to Check Before Narrowing

Instead of casting and hoping no data is lost, **check the range before casting**.

~~~java
static boolean fitsInByte(long value) {
    return value >= Byte.MIN_VALUE && value <= Byte.MAX_VALUE;
}

static byte toByteChecked(long value) {
    if (!fitsInByte(value)) {
        throw new IllegalArgumentException("Out of byte range: " + value);
    }
    return (byte) value;
}
~~~

Example:

~~~java
System.out.println(fitsInByte(127));  // true
System.out.println(fitsInByte(128));  // false
System.out.println(toByteChecked(127)); // 127
~~~

If replaced with `(byte) 128` without checking, the result becomes `-128`, because narrowing keeps the low bits and interprets them as a signed `byte`.

Wrapper limits make checks clearer than hardcoding `-128`/`127`, especially if the parameter type changes later or values are read externally.

### Use Built-In Checked Conversion APIs

When converting a `long` to an `int`, you also have:

~~~java
long input = (long) Integer.MAX_VALUE + 1L;
// int invalid = Math.toIntExact(input); // Throws ArithmeticException at runtime
~~~

`Math.toIntExact` reports overflow instead of silently truncating bits. It does not replace defining which values are valid under business rules, but it prevents a common data-loss bug.


## 8. Applying `BYTES`: Describing a Binary Record

The `SIZE`/`BYTES` constants are useful when you need to know **how many bytes of value data** will be written to a binary format. For example, a record containing one `int` and one `long` needs `Integer.BYTES + Long.BYTES == 12` bytes for the two values (excluding any header/metadata if the format adds them).

~~~java
import java.nio.ByteBuffer;

public class BinaryRecordSizeDemo {
    public static void main(String[] args) {
        ByteBuffer record = ByteBuffer.allocate(Integer.BYTES + Long.BYTES);
        record.putInt(42);
        record.putLong(9_000_000_000L);
        System.out.println(record.position()); // 12
    }
}
~~~

Compile and run `BinaryRecordSizeDemo.java` to verify the output `12`. `ByteBuffer` uses big-endian byte order by default; when reading/writing network or file formats, you must agree on byte order with the other party. `BYTES` does not tell you the actual size of an `Integer`, `Long`, or `ByteBuffer` object in JVM memory.

Type limits also do not automatically detect overflow: `Integer.MAX_VALUE + 1` still wraps around during `int` addition; if reliable results are required, check the range or use `Math.*Exact`. The program below includes examples verifying these boundary cases.

## 9. Complete Java 17 Example — Inspecting Limits and Detecting Out-of-Range Values

Create the file **`PrimitiveLimitsDemo.java`** with the following code:

~~~java
public final class PrimitiveLimitsDemo {
    private PrimitiveLimitsDemo() {}

    static boolean fitsInByte(long value) {
        return value >= Byte.MIN_VALUE && value <= Byte.MAX_VALUE;
    }

    static byte toByteChecked(long value) {
        if (!fitsInByte(value)) {
            throw new IllegalArgumentException("Out of byte range: " + value);
        }
        return (byte) value;
    }

    public static void main(String[] args) {
        System.out.println("byte: " + Byte.MIN_VALUE
                + ".." + Byte.MAX_VALUE + ", " + Byte.SIZE + " bits");
        System.out.println("short: " + Short.MIN_VALUE
                + ".." + Short.MAX_VALUE + ", " + Short.SIZE + " bits");
        System.out.println("int: " + Integer.MIN_VALUE
                + ".." + Integer.MAX_VALUE + ", " + Integer.SIZE + " bits");
        System.out.println("long: " + Long.MIN_VALUE
                + ".." + Long.MAX_VALUE + ", " + Long.SIZE + " bits");

        System.out.println("char code units: "
                + (int) Character.MIN_VALUE + ".."
                + (int) Character.MAX_VALUE
                + ", " + Character.SIZE + " bits");
        System.out.println("byte bytes=" + Byte.BYTES);
        System.out.println("int bytes=" + Integer.BYTES);

        System.out.println("float: " + Float.SIZE + " bits"
                + ", min positive=" + Float.MIN_VALUE
                + ", max finite=" + Float.MAX_VALUE);
        System.out.println("float min normal=" + Float.MIN_NORMAL);
        System.out.println("double: " + Double.SIZE + " bits"
                + ", min positive=" + Double.MIN_VALUE
                + ", max finite=" + Double.MAX_VALUE);

        System.out.println("fits 127=" + fitsInByte(127));
        System.out.println("fits 128=" + fitsInByte(128));
        System.out.println("checked byte=" + toByteChecked(127));
        try {
            toByteChecked(128);
        } catch (IllegalArgumentException ex) {
            System.out.println("range error=" + ex.getMessage());
        }

        System.out.println("int wrapped=" + (Integer.MAX_VALUE + 1));
        System.out.println("abs int min=" + Math.abs(Integer.MIN_VALUE));

        try {
            Math.addExact(Integer.MAX_VALUE, 1);
        } catch (ArithmeticException ex) {
            System.out.println("checked add=overflow");
        }

        try {
            Math.toIntExact((long) Integer.MAX_VALUE + 1L);
        } catch (ArithmeticException ex) {
            System.out.println("checked narrowing=overflow");
        }

        double tooLarge = Double.MAX_VALUE * 2.0;
        System.out.println("finite overflow=" + tooLarge);
        System.out.println("is finite=" + Double.isFinite(tooLarge));
    }
}
~~~

Open a terminal in the directory containing the file and use **JDK 17 or later**.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 PrimitiveLimitsDemo.java
java -cp . PrimitiveLimitsDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\PrimitiveLimitsDemo.java
java -cp . PrimitiveLimitsDemo
~~~

**Exact expected output:**

~~~text
byte: -128..127, 8 bits
short: -32768..32767, 16 bits
int: -2147483648..2147483647, 32 bits
long: -9223372036854775808..9223372036854775807, 64 bits
char code units: 0..65535, 16 bits
byte bytes=1
int bytes=4
float: 32 bits, min positive=1.4E-45, max finite=3.4028235E38
float min normal=1.17549435E-38
double: 64 bits, min positive=4.9E-324, max finite=1.7976931348623157E308
fits 127=true
fits 128=false
checked byte=127
range error=Out of byte range: 128
int wrapped=-2147483648
abs int min=-2147483648
checked add=overflow
checked narrowing=overflow
finite overflow=Infinity
is finite=false
~~~

Every line in the example is produced by standard JDK APIs and constants; it does not depend on data files or external libraries. The output is the expected result for self-verification after compiling/running.

## 10. Common Misconceptions

| Statement/code | Problem | Correct understanding |
|---|---|---|
| `Byte.MAX_VALUE == 255` | Wrong, `byte` is signed | `Byte.MAX_VALUE == 127` |
| `Integer.SIZE == 4` | Confuses bits with bytes | `Integer.SIZE == 32`; `Integer.BYTES == 4` |
| `Long.MIN_VALUE == -Long.MAX_VALUE` | Forgets the negative range has one extra value | `Long.MIN_VALUE == -Long.MAX_VALUE - 1` |
| `Float.MIN_VALUE` is negative infinity or the lowest negative value | Wrong meaning of floating-point constant | It is the smallest non-zero **positive** number |
| `Double.MAX_VALUE` equals `Infinity` | Confuses a finite value with infinity | `Double.isFinite(Double.MAX_VALUE)` is true |
| `Character.SIZE == 8` | `char` uses a UTF-16 code unit | `Character.SIZE == 16` |
| `Boolean.SIZE` exists | Java does not declare such a constant | Only true/false, no `Boolean.SIZE` |
| `(byte) 128` stays 128 | Narrowing cast truncates bits | The result is -128 |
| `Integer.MAX_VALUE + 1` automatically widens to long | Operands are still int | int overflow, result is `Integer.MIN_VALUE` |
| `Math.abs(Integer.MIN_VALUE)` is always positive | Absolute value does not fit in int | Result is still `Integer.MIN_VALUE` |

### Rules for Validating Floating-Point Input

If a user supplies an external `double` value, distinguish:

- **Invalid format**: cannot be parsed as a number.
- **Non-finite**: `NaN` or `Infinity`.
- **Finite but outside business range**: e.g., negative quantity or exceeding allowed limits.

A type's `MIN_VALUE`/`MAX_VALUE` **does not automatically define the business domain**. For instance, a product quantity must be non-negative and might be constrained from 0 to 100, not necessarily using the entire `int` range.

## 11. Exercises with Answers

### Exercise A — Distinguishing Bits and Bytes

Find `Short.SIZE`, `Short.BYTES`, `Long.SIZE`, `Long.BYTES`.

**Answer:** `16`, `2`, `64`, `8` respectively.

### Exercise B — Limits of `char`

~~~java
System.out.println((int) Character.MAX_VALUE);
System.out.println(Character.SIZE);
~~~

**Answer:**

~~~text
65535
16
~~~

Because `char` is a 16-bit UTF-16 code unit, distinct from signed `short`.

### Exercise C — Limits of `float`

Is `Float.MIN_VALUE` negative? What should you use to represent the smallest finite negative number in numerical order?

**Answer:** no; `Float.MIN_VALUE` is the smallest positive non-zero subnormal number. The lowest finite negative number is `-Float.MAX_VALUE`.

### Exercise D — Narrowing Casts

~~~java
System.out.println((byte) 128);
System.out.println((byte) 255);
~~~

**Answer:**

~~~text
-128
-1
~~~

The data exceeds the byte range, and the low bits are kept according to conversion rules.

### Exercise E — Checking Overflow

You want to increment `Integer.MAX_VALUE` by 1, but **must report an error on overflow**. Should you use ordinary addition or `Math.addExact`?

**Answer:** use `Math.addExact(Integer.MAX_VALUE, 1)` and handle `ArithmeticException`; ordinary `+` yields the overflowed value.

### Exercise F — Business Limits

An input `int age = -5;` is valid within the `int` range, but is it valid as an age?

**Answer:** no. `Integer.MIN_VALUE`/`MAX_VALUE` only bound **the type's representational capacity**; the business domain of age must be checked with a separate condition.

## 12. Completion Checklist

- [ ] Remember that `Byte`, `Short`, `Integer`, and `Long` have `MIN_VALUE`, `MAX_VALUE`, and `SIZE`.
- [ ] Read `byte`/`short`/`int`/`long` limits accurately as signed types.
- [ ] Know that `SIZE` is the bit count and `BYTES` is the byte count of the value representation.
- [ ] Understand that `Character.SIZE == 16` and `char` is a UTF-16 code unit.
- [ ] Distinguish `Float.MIN_VALUE`/`Double.MIN_VALUE` from the lowest finite negative number.
- [ ] Know that floating-point `MIN_NORMAL` differs from `MIN_VALUE`.
- [ ] Know that `Boolean` has no `MIN_VALUE`, `MAX_VALUE`, or `SIZE`.
- [ ] Check range before narrowing casts and watch out for overflow.
- [ ] Do not confuse type limits with valid business value ranges.
- [ ] Compile and run `PrimitiveLimitsDemo.java` with Java 17+, and verify the output.

**Conclusion:** `MIN_VALUE`, `MAX_VALUE`, and `SIZE` let you look up limits and value widths **accurately according to the Java specification**, avoiding hardcoded magic numbers and aiding validation. For integers, `MIN_VALUE` is the smallest negative number; for `float`/`double`, `MIN_VALUE` is the **smallest positive non-zero** number. Always distinguish bits from bytes, representational capacity from business requirements, and check operations that may overflow.
