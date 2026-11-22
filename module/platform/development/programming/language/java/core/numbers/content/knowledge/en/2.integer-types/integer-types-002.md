# Bit Size and Value Range of Each Integer Type in Java

## 1. Why Must You Know Bit Width and Value Range?

Each primitive integral type in Java has a **fixed bit width**. That width determines how many distinct bit patterns exist, and how Java interprets those bits determines the **minimum and maximum values** that can be stored.

For example, 8 bits have \(2^8 = 256\) combinations. With the signed `byte` type, Java assigns those combinations to the values from **-128 to 127**, rather than from 0 to 255. Understanding this rule helps you:

- Choose the right type for your data and avoid accidentally going out of range.
- Explain why arithmetic operations can **overflow** and produce unexpected results.
- Understand **casting**, bitwise operations, and binary data.
- Distinguish a **primitive type** from a **wrapper** class object.

This lesson covers the primitive integral types `byte`, `short`, `int`, `long`, and `char`. The first four are **signed** integers; `char` is an **unsigned** integral value used as a UTF-16 code unit. `boolean` only accepts `true/false` and does not belong to the integer table.

## 2. Table of Bit Widths and Value Ranges

| Type | Bits | Bytes | Minimum Value | Maximum Value | Distinct Values |
|---|---:|---:|---:|---:|---:|
| `byte` | 8 | 1 | -128 | 127 | \(2^8 = 256\) |
| `short` | 16 | 2 | -32_768 | 32_767 | \(2^{16} = 65\,536\) |
| `int` | 32 | 4 | -2_147_483_648 | 2_147_483_647 | \(2^{32}\) |
| `long` | 64 | 8 | -9_223_372_036_854_775_808 | 9_223_372_036_854_775_807 | \(2^{64}\) |
| `char` | 16 | 2 | 0 (U+0000) | 65_535 (U+FFFF) | \(2^{16} = 65\,536\) |

**These are widths specified by Java**, identical on both 32-bit and 64-bit JVMs. A Java `int` is always 32 bits, independent of the size of `int` in C on different platforms.

The bit width of a primitive type is also **not synonymous** with the size of an `Integer` or `Long` object on the heap. Objects have headers, alignment, and other overhead; you cannot take 32 bits and conclude that an `Integer` object uses 4 bytes of memory.

In Java, 1 byte consists of 8 bits. The wrapper classes expose corresponding constants: `Byte.SIZE/BYTES`, `Short.SIZE/BYTES`, `Integer.SIZE/BYTES`, `Long.SIZE/BYTES`, `Character.SIZE/BYTES`; the value ranges are in `MIN_VALUE` and `MAX_VALUE`. These constants are useful for reference, but the key is understanding **how they are calculated and what they mean**.

## 3. Deriving the Value Range from Bit Width

### 3.1. Signed Types: Two's Complement

For a signed type that is **n bits** wide (`byte`, `short`, `int`, `long`), Java uses two's complement representation. The value range is:

\[
\boxed{-2^{n-1} \le x \le 2^{n-1}-1}
\]

- **Lower bound**: \(-2^{n-1}\).
- **Upper bound**: \(2^{n-1}-1\).
- **Number of representable values**: \(2^n\), including 0.

Applied to `byte` (\(n=8\)): \(-2^7=-128\) to \(2^7-1=127\).

Applied to `short` (\(n=16\)): \(-2^{15}=-32\,768\) to \(2^{15}-1=32\,767\).

Applied to `int` (\(n=32\)): \(-2^{31}\) to \(2^{31}-1\).

Applied to `long` (\(n=64\)): \(-2^{63}\) to \(2^{63}-1\).

**Why is the absolute value of the negative bound one greater than the positive bound?** Because 0 occupies one value in the non-negative set. For example, `byte` has 128 negative values (-128 to -1) and 128 non-negative values (0 to 127). Therefore, there is no positive `byte` value +128 to mirror -128.

### 3.2. Looking at 8-Bit Patterns

For `byte`, some examples:

| Bit pattern (8-bit) | Signed `byte` interpretation |
|---|---:|
| `0000 0000` | 0 |
| `0000 0001` | 1 |
| `0111 1111` | 127 |
| `1000 0000` | -128 |
| `1111 1111` | -1 |

The highest bit has weight \(-2^7\) in 8-bit two's complement representation, and the remaining bits have weights \(2^6,\ldots,2^0\). Thus `1000 0000` is -128; `1111 1111` is \(-128+64+32+16+8+4+2+1=-1\).

Practical rule of thumb: negate a number in two's complement by **inverting all bits and adding 1, within the exact n-bit width**. For example, the 8 bits of +1 are `0000 0001`; inverting the bits gives `1111 1110`, and adding 1 yields `1111 1111`, which is -1.

In Java, the results of bitwise expressions on `byte` are usually **promoted to `int`**, so when practicing bitwise inversion `~`, you must account for bit width and casting. Do not assume `~((byte)1)` automatically stays 8 bits: that expression has type `int`.

### 3.3. `char`: 16 Bits, but Unsigned

`char` is 16 bits, but its value range is:

\[
0 \le \texttt{char} \le 2^{16}-1 = 65535
\]

It represents a **UTF-16 code unit**, not a 16-bit signed integer like `short`. Thus the two types are both 16 bits wide yet have different ranges:

- `short`: -32_768 to 32_767.
- `char`: 0 to 65_535.

A Unicode character outside the Basic Multilingual Plane (BMP), such as an emoji, requires a **surrogate pair of two `char`s**. Therefore, one Unicode code point does not necessarily match one `char`. To count characters by code point, use `String.codePointCount(...)` or `String.codePoints()`, instead of assuming `String.length()` is the number of visible characters.

## 4. Running Java to Observe

Create the file `PrimitiveRangeDemo.java`:

```java
public class PrimitiveRangeDemo {
    public static void main(String[] args) {
        System.out.printf("byte: %d..%d (%d bits)%n",
                Byte.MIN_VALUE, Byte.MAX_VALUE, Byte.SIZE);
        System.out.printf("short: %d..%d (%d bits)%n",
                Short.MIN_VALUE, Short.MAX_VALUE, Short.SIZE);
        System.out.printf("int: %d..%d (%d bits)%n",
                Integer.MIN_VALUE, Integer.MAX_VALUE, Integer.SIZE);
        System.out.printf("long: %d..%d (%d bits)%n",
                Long.MIN_VALUE, Long.MAX_VALUE, Long.SIZE);
        System.out.printf("char: %d..%d (%d bits)%n",
                (int) Character.MIN_VALUE, (int) Character.MAX_VALUE,
                Character.SIZE);

        System.out.println("int bytes: " + Integer.BYTES);
        System.out.println("char bytes: " + Character.BYTES);
    }
}
```

Compile and run with Java 17+:

```bash
javac PrimitiveRangeDemo.java
java PrimitiveRangeDemo
```

Output:

```text
byte: -128..127 (8 bits)
short: -32768..32767 (16 bits)
int: -2147483648..2147483647 (32 bits)
long: -9223372036854775808..9223372036854775807 (64 bits)
char: 0..65535 (16 bits)
int bytes: 4
char bytes: 2
```

The two `(int)` casts on the `char` line are used to print the **numeric value** of the code unit. If you print `Character.MIN_VALUE` directly as a character, you may get an invisible control character.

## 5. Going Out of Range: Overflow and Casting

### 5.1. Arithmetic Overflow

An `int` can only store up to 2_147_483_647. When you add 1 using `int` addition, the result wraps around to -2_147_483_648 under modulo \(2^{32}\) arithmetic. Ordinary integer addition **does not automatically throw an exception**.

Distinguish between two points in time when widening to `long`:

- `(long) (max + 1)`: the addition **already ran in `int` and overflowed** before the type conversion.
- `(long) max + 1`: `max` is converted to `long` **before the addition**, so there is enough range to represent the result.

### 5.2. Narrowing Conversion

Casting `int` 128 to `byte` keeps the low 8 bits of the value, reinterprets them in the 8-bit signed range, and yields **-128**. Direct casting does not check the range to throw an error.

For constant assignment, the compiler allows direct assignment `byte b = 127;` because 127 is within the `byte` range; however, `byte b = 128;` is a compile error because it exceeds the range, unless you explicitly cast it.

### 5.3. Runnable Example

Create the file `BoundaryDemo.java`:

```java
public class BoundaryDemo {
    public static void main(String[] args) {
        int max = Integer.MAX_VALUE;

        System.out.println("int max + 1 = " + (max + 1));
        System.out.println("widen after = " + (long) (max + 1));
        System.out.println("widen before = " + ((long) max + 1));
        System.out.println("(byte) 128 = " + (byte) 128);
        System.out.println("byte max + 1 = " + (Byte.MAX_VALUE + 1));

        try {
            System.out.println(Math.addExact(max, 1));
        } catch (ArithmeticException e) {
            System.out.println("addExact: overflow");
        }

        long outsideInt = 2_147_483_648L;
        try {
            System.out.println(Math.toIntExact(outsideInt));
        } catch (ArithmeticException e) {
            System.out.println("toIntExact: out of int range");
        }
    }
}
```

Run:

```bash
javac BoundaryDemo.java
java BoundaryDemo
```

Output:

```text
int max + 1 = -2147483648
widen after = -2147483648
widen before = 2147483648
(byte) 128 = -128
byte max + 1 = 128
addExact: overflow
toIntExact: out of int range
```

`Byte.MAX_VALUE + 1` prints 128 because the addition operator **promotes `byte` to `int`**, so the addition result has type `int`. 8-bit overflow only happens if you cast the result back to `byte` or compute directly in a narrowed type.

The methods `Math.addExact`, `Math.subtractExact`, `Math.multiplyExact`, `Math.negateExact`, and `Math.toIntExact` help detect the corresponding overflow/out-of-range cases. They throw `ArithmeticException` when the result cannot be represented.

## 6. Integer Notation and Limits to Remember

### 6.1. `int` and `long` Literals

By default, an unsuffixed decimal integer literal is `int` when valid; add `L` to write a `long`:

```java
int population = 2_000_000_000;
long bigger = 3_000_000_000L;
long maximum = Long.MAX_VALUE;
```

Writing `3_000_000_000` without the `L` suffix causes an error because it exceeds the `int` literal range, even if the left-hand side is declared as `long`. Underscores in numbers only aid readability; they do not change the value or type.

The two minimum negative values `-2147483648` and `-9223372036854775808L` have special lexical rules in Java for the unary minus operator; to avoid confusion, prefer `Integer.MIN_VALUE` and `Long.MIN_VALUE` in application code.

### 6.2. Some Boundary Pitfalls

- `Math.abs(Integer.MIN_VALUE)` still equals `Integer.MIN_VALUE`, which is negative, because +2_147_483_648 exceeds the `int` range. The same applies to `Long.MIN_VALUE`.
- `-Integer.MIN_VALUE` still equals `Integer.MIN_VALUE` due to overflow when negating.
- `Integer.MIN_VALUE / -1` returns `Integer.MIN_VALUE` because the positive quotient cannot be represented in `int`.
- Converting an expression to `long` **after the calculation has overflowed** does not recover the original result.
- `SIZE/BYTES` represent the width of the **primitive value**, not the total memory of an array, wrapper object, or data structure (which also depends on overhead, alignment, and the VM).

If an integer can exceed the `long` range, use `java.math.BigInteger`. It does not have a fixed 64-bit width, so it does not have fixed MIN/MAX bounds like primitive types.

## 7. Are There `unsigned int` and `unsigned long` Types?

Java **does not have separate primitive types named `unsigned int` or `unsigned long`**. However, Java supports operations that *interpret bit patterns* from an unsigned perspective:

- Unsigned 32-bit has the range **0 to 4_294_967_295**, i.e., \(0\) to \(2^{32}-1\).
- Unsigned 64-bit has the range **0 to 18_446_744_073_709_551_615**, i.e., \(0\) to \(2^{64}-1\); this highest value exceeds the signed `long` range.
- Supporting APIs include `Integer.compareUnsigned`, `Integer.divideUnsigned`, `Integer.toUnsignedLong`, `Integer.toUnsignedString`, along with `Long.compareUnsigned`, `Long.divideUnsigned`, and `Long.toUnsignedString`.

Example:

```java
System.out.println(Integer.toUnsignedLong(-1));
System.out.println(Integer.toUnsignedString(-1));
```

Both lines print `4294967295`. The bit pattern `0xFFFF_FFFF` can be understood as -1 if interpreted as a signed `int`, or 4_294_967_295 if interpreted as an unsigned 32-bit value. The unsigned APIs **do not change the 32-bit or 64-bit width** of the value stored in the variable.

As for `char`, it is inherently an unsigned 16-bit type used for UTF-16 code units; do not use `char` as a substitute for general unsigned integers just because it shares the same width as `short`.

## 8. Choosing Data Types and Validating Input

**`byte`** is suitable when you need to represent values in -128..127 or manipulate binary bytes. When you want a 0..255 value from a binary byte, look at `Byte.toUnsignedInt(...)` or `b & 0xFF`.

**`short`** is suitable when an API, file format, or protocol specifies exact 16-bit signed integers; in ordinary business calculations, `int` is simpler and more common.

**`int`** is the usual choice for indices, counters, and 32-bit integers with clear bounds. For Java array indices, `int` is the standard type used; array size is also limited by the JVM/memory, not solely by `Integer.MAX_VALUE`.

**`long`** is used when a larger range is needed, such as large counts, milliseconds from an epoch, or data quantities that might exceed 32 bits. Even so, `long` is still finite: if calculations risk exceeding 64 bits, consider `BigInteger` or overflow checks.

**`char`** is used when working at the UTF-16 code unit level; if you need to handle **Unicode code points**, choose code-point traversal APIs to avoid splitting surrogate pairs.

When receiving external data and casting to a narrower type, validate the value before converting:

```java
static byte requireByteRange(int value) {
    if (value < Byte.MIN_VALUE || value > Byte.MAX_VALUE) {
        throw new IllegalArgumentException("outside byte range");
    }
    return (byte) value;
}
```

This is an **illustrative method snippet** (placed inside a class to use), not a standalone program with `main`. The key point is to check **before** casting: if you cast first, important bits of data may already be lost.

## 9. Self-Check Knowledge Quiz

1. **How many bit patterns do 8 bits have?** — \(2^8=256\) patterns.
2. **Why does `byte` have the range -128..127 instead of -127..127?** — Under two's complement, 8 bits encode 128 negative values and 128 non-negative values; 0 already occupies one pattern.
3. **`short` and `char` are both 16 bits; are their ranges the same?** — No. `short` is signed: -32_768..32_767; `char` is unsigned: 0..65_535.
4. **Can a 32-bit `int` hold the value 3_000_000_000?** — Not under signed interpretation. You can use `long` or interpret the bit pattern as unsigned using the corresponding API.
5. **Why does `long result = Integer.MAX_VALUE + 1;` still yield a negative result?** — Both operands are added as `int` first, causing overflow; the negative result is only then widened to `long`. Use `long result = (long) Integer.MAX_VALUE + 1;`.
6. **Does an emoji necessarily take only 1 `char` because `char` is 16 bits?** — No. Unicode code points outside the BMP usually require two UTF-16 code units, i.e., two `char`s.
7. **Does `long` guarantee that every integer can be stored?** — No. The signed `long` range is only from \(-2^{63}\) to \(2^{63}-1\); larger numbers require another representation such as `BigInteger`.

**Core takeaway:** An **n-bit** width gives \(2^n\) bit patterns; for **signed** types, the range is \([-2^{n-1},2^{n-1}-1]\); for **16-bit unsigned** `char`, the range is \([0,2^{16}-1]\). Always identify **the types actually participating in the operation** before reasoning about overflow or type conversion.
