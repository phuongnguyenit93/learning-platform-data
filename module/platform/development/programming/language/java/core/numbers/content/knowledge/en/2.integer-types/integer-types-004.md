# MIN_VALUE, MAX_VALUE, SIZE, and BYTES of Integer Types in Java

## 1. What Are the Four Constants For?

When working with integers, you need to know the **value range** a data type can represent and its **fixed width**. Java exposes these four pieces of information through the wrapper classes in `java.lang`:

- `MIN_VALUE`: the smallest representable value.
- `MAX_VALUE`: the largest representable value.
- `SIZE`: the number of **bits** of the corresponding primitive type.
- `BYTES`: the number of **bytes** of the corresponding primitive type, where 1 byte = 8 bits.

These constant names belong to the wrapper classes, such as `Integer.MIN_VALUE`, **not to the primitive type keyword** `int`. They are `public static final` fields that can be accessed without creating an object. The sizes below are specified by the Java language, independent of operating system and CPU architecture.

## 2. Complete Reference Table

| Primitive type | Wrapper class | `MIN_VALUE` | `MAX_VALUE` | `SIZE` (bits) | `BYTES` (bytes) |
|---|---|---:|---:|---:|---:|
| `byte` | `Byte` | -128 | 127 | 8 | 1 |
| `short` | `Short` | -32_768 | 32_767 | 16 | 2 |
| `int` | `Integer` | -2_147_483_648 | 2_147_483_647 | 32 | 4 |
| `long` | `Long` | -9_223_372_036_854_775_808 | 9_223_372_036_854_775_807 | 64 | 8 |
| `char` | `Character` | U+0000 (numeric value 0) | U+FFFF (numeric value 65_535) | 16 | 2 |

The four types `byte`, `short`, `int`, and `long` are **signed integers**. For a type of width `n` bits:

- Minimum: \(-2^{n-1}\).
- Maximum: \(2^{n-1}-1\).
- Total bit patterns: \(2^n\); there is one more negative value than positive value because of 0.

`char` is also a primitive integral type in Java, but **unsigned**: it stores a *UTF-16 code unit* from 0 to 65_535, primarily for handling characters. A Unicode character outside the BMP may require **two `char`s** (a surrogate pair), so `Character.SIZE = 16` does not mean every Unicode character is always 16 bits long.

`boolean` does not have a corresponding `MIN_VALUE/MAX_VALUE/SIZE/BYTES` set of constants; do not infer the memory size of `boolean` from this table.

## 3. Reading the Constants Directly in a Program

Save the file `IntegerMetadataDemo.java`:

```java
public class IntegerMetadataDemo {
    public static void main(String[] args) {
        System.out.printf("byte: [%d, %d], SIZE=%d, BYTES=%d%n",
                Byte.MIN_VALUE, Byte.MAX_VALUE, Byte.SIZE, Byte.BYTES);
        System.out.printf("short: [%d, %d], SIZE=%d, BYTES=%d%n",
                Short.MIN_VALUE, Short.MAX_VALUE, Short.SIZE, Short.BYTES);
        System.out.printf("int: [%d, %d], SIZE=%d, BYTES=%d%n",
                Integer.MIN_VALUE, Integer.MAX_VALUE, Integer.SIZE, Integer.BYTES);
        System.out.printf("long: [%d, %d], SIZE=%d, BYTES=%d%n",
                Long.MIN_VALUE, Long.MAX_VALUE, Long.SIZE, Long.BYTES);
        System.out.printf("char: [%d, %d], SIZE=%d, BYTES=%d%n",
                (int) Character.MIN_VALUE, (int) Character.MAX_VALUE,
                Character.SIZE, Character.BYTES);
    }
}
```

Compile and run with Java 17+:

```bash
javac IntegerMetadataDemo.java
java IntegerMetadataDemo
```

Output:

```text
byte: [-128, 127], SIZE=8, BYTES=1
short: [-32768, 32767], SIZE=16, BYTES=2
int: [-2147483648, 2147483647], SIZE=32, BYTES=4
long: [-9223372036854775808, 9223372036854775807], SIZE=64, BYTES=8
char: [0, 65535], SIZE=16, BYTES=2
```

The two `(int)` casts on the `char` line print the **numeric code unit value** instead of an invisible character. For signed types, `MIN_VALUE/MAX_VALUE` are numeric values; `SIZE/BYTES` describe the width of the primitive type, not the size of an `Integer`, `Long`, etc. object.

## 4. When to Use Each Constant?

### 4.1. `MIN_VALUE` and `MAX_VALUE`: Range Checking

Suppose the input data is a `long` but the target API only accepts an `int`. Before casting, check:

```java
boolean fitsInt = value >= Integer.MIN_VALUE
        && value <= Integer.MAX_VALUE;
```

If it is not within that range, the cast `(int) value` will **discard the high bits** and may turn it into another value without automatically reporting an error. Java also provides `Math.toIntExact(long)` for checked conversion, which throws `ArithmeticException` when outside the `int` range.

For signed integer addition, subtraction, and multiplication, use `Math.addExact`, `Math.subtractExact`, and `Math.multiplyExact` when you want to detect overflow rather than receive a *wraparound* result.

Save the file `SafeIntegerDemo.java`:

```java
public class SafeIntegerDemo {
    public static void main(String[] args) {
        long value = 2_147_483_648L; // int MAX_VALUE + 1

        boolean fitsInt = value >= Integer.MIN_VALUE
                && value <= Integer.MAX_VALUE;
        System.out.println("fits int: " + fitsInt);
        System.out.println("cast (int): " + (int) value);

        try {
            Math.toIntExact(value);
        } catch (ArithmeticException e) {
            System.out.println("toIntExact: overflow");
        }

        try {
            Math.addExact(Integer.MAX_VALUE, 1);
        } catch (ArithmeticException e) {
            System.out.println("addExact: overflow");
        }
    }
}
```

Run:

```bash
javac SafeIntegerDemo.java
java SafeIntegerDemo
```

Exact output:

```text
fits int: false
cast (int): -2147483648
toIntExact: overflow
addExact: overflow
```

**Note:** range checking with `MIN_VALUE/MAX_VALUE` works when the input value is in a wider type. If arithmetic has already overflowed inside `int` and you only compare with `Integer.MAX_VALUE` afterward, it is already too late: the variable only holds the post-overflow result.

### 4.2. `SIZE`: Working with Bits

`Integer.SIZE` is always 32, and `Long.SIZE` is always 64. These constants are useful for bit algorithms, masks, binary protocols, and bit representations:

```java
int bitCount = Integer.SIZE;  // 32
int highBitMask = 1 << (Integer.SIZE - 1); // sign bit of int
long twoTo32 = 1L << Integer.SIZE; // 4294967296L
```

Do not write `1 << 32` to compute \(2^{32}\): the `int` left-hand operand makes Java use only the low 5 bits of the shift distance; `1 << 32` is equivalent to `1 << 0` and equals **1**. Use `1L` when the shift must be computed as `long`.

### 4.3. `BYTES`: Determining Binary Data Width

`Integer.BYTES` is 4 and `Long.BYTES` is 8. For example, a binary record consisting of one `int` and one `long` has a total payload data width of:

```java
int recordBytes = Integer.BYTES + Long.BYTES; // 12
```

When transmitting data, you also need to specify **byte order** (*endianness*). For instance, `ByteBuffer` uses big-endian by default and can be switched via `order(ByteOrder.LITTLE_ENDIAN)`. `BYTES` only states the byte count, not the byte order, and **does not include** headers, padding, object memory, or collection overhead.

## 5. Common Pitfalls

### 5.1. Overflow Does Not Automatically Throw an Exception

```java
int wrapped = Integer.MAX_VALUE + 1; // -2147483648
long wrappedLong = Long.MAX_VALUE + 1; // Long.MIN_VALUE
```

Signed integer addition in Java produces a result within the fixed bit width; to raise an error, use the `Exact` methods or switch to `BigInteger` if you need integers not limited to 64 bits.

### 5.2. `MIN_VALUE` Is Asymmetric with `MAX_VALUE`

Because there is one more negative value than positive value:

```java
System.out.println(-Integer.MIN_VALUE);
System.out.println(Math.abs(Integer.MIN_VALUE));
```

Both lines print `-2147483648` because the positive result cannot be represented in `int`. Similarly, `Integer.MIN_VALUE / -1` returns `Integer.MIN_VALUE` (a special overflow case of integer division). Use `Math.negateExact` if you need to catch an error when negating; for the absolute value of the minimum value, use a wider type or `BigInteger`.

### 5.3. Constants Belong to Wrapper Classes, Not Object Memory Size

`Integer.BYTES == 4` describes a **32-bit `int` value**. It does not promise that a `new Integer(...)` object occupies exactly 4 bytes; object headers, alignment, and VM internals make its footprint different. In modern Java, you should also use `Integer.valueOf(...)` or autoboxing, avoiding deprecated wrapper constructors.

### 5.4. Casting, Numeric Promotion, and `long` Literals

- In arithmetic expressions, `byte`, `short`, and `char` are usually promoted to `int`: `Byte.MAX_VALUE + 1` has type `int` and equals 128.
- `(byte) 128` yields -128 because it keeps the low 8 bits.
- `long` literals should have the `L` suffix: `3_000_000_000L`; underscores only improve readability and do not change the value.
- For unsigned integers stored in `int/long` bits, look at APIs such as `Integer.compareUnsigned`, `Integer.toUnsignedLong`, and `Long.compareUnsigned`. Do not infer unsigned bounds from `Integer.MIN_VALUE/MAX_VALUE` because those two constants are **signed** bounds.

### 5.5. Do Not Confuse `Integer.MIN_VALUE` with `Double.MIN_VALUE`

`Integer.MIN_VALUE` is the **most negative number** of `int`. In contrast, `Float.MIN_VALUE` and `Double.MIN_VALUE` are the **smallest positive non-zero values** representable (subnormal values), not the most negative numbers. For floating-point numbers, you must also consider `MAX_VALUE`, negative signs, infinity, NaN, and precision; do not mechanically apply the integer table.

## 6. How to Choose and Use in Practice

1. Choose `int` for everyday integers within the 32-bit range; use `long` for larger numbers or timestamps/counts that may exceed the `int` limit.
2. When receiving large data and converting to a narrower type, validate the range with `MIN_VALUE/MAX_VALUE` or `Math.toIntExact`.
3. When arithmetic overflow would cause a business logic error, use `Math.*Exact` operations and handle the exception appropriately.
4. When manipulating bits or binary formats, read `SIZE/BYTES` from the wrapper to make the width explicit; specify the data format's endianness.
5. For numbers larger than the `long` limit, use `java.math.BigInteger`; `BigInteger` has no corresponding fixed `MIN_VALUE/MAX_VALUE/SIZE/BYTES` constants because its magnitude can grow.

## 7. Self-Check

**Question 1.** What are `Short.SIZE` and `Short.BYTES` respectively?  
**Answer:** 16 bits and 2 bytes.

**Question 2.** Why is `Integer.MIN_VALUE` equal to -2_147_483_648 while `Integer.MAX_VALUE` is only 2_147_483_647?  
**Answer:** one of the 32 bits is reserved for the sign; the signed 32-bit range is \([-2^{31},2^{31}-1]\), including 0.

**Question 3.** Does casting `2_147_483_648L` to `int` throw an exception?  
**Answer:** no; direct casting yields -2_147_483_648. `Math.toIntExact` will throw `ArithmeticException`.

**Question 4.** Does `Character.SIZE = 16` guarantee every Unicode character fits in one `char`?  
**Answer:** no; a code point outside the BMP requires two UTF-16 code units, i.e., two `char`s.

**Question 5.** Can `Integer.BYTES` be used to measure the memory of an `Integer` object?  
**Answer:** no; it is the width of the primitive `int` value, not the size of the object on the heap.

**Remember:** `MIN_VALUE/MAX_VALUE` answer **what values can be represented?**; `SIZE/BYTES` answer **how many bits/bytes wide is the primitive type?**. These are two groups of constants with different purposes, though they are often used together for safe integer handling and properly formatted binary data.
