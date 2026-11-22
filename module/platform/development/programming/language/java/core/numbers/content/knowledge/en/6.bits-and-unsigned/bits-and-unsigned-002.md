# Left Shift `<<`, Right Shift `>>`, and Unsigned Right Shift `>>>` in Java

## 1. What Problem Do the Three Shift Operators Solve?

In Java, the *bitwise shift operators* move the bits of an integer value by a specified number of positions:

- **`x << n` — *left shift***: shifts the bits of `x` left by `n` positions, filling the vacated positions on the right with `0` bits; bits shifted past the type's width are discarded.
- **`x >> n` — *signed/arithmetic right shift***: shifts the bits to the right; vacated positions on the left are filled with the operand's **sign bit** (`0` if non-negative, `1` if negative).
- **`x >>> n` — *unsigned/logical right shift***: shifts the bits to the right; vacated positions on the left are **always filled with `0`**.

All three operate on the **bit pattern** of an integer and produce a result of an integer type. `>>>` does not create a new `unsigned int` type: Java has no primitive type by that name.

| Shift | Direction | Fill bit in vacated positions | Key takeaway |
|---|---|---|---|
| `<<` | Left | `0` from the right | Can lose high bits or change sign |
| `>>` | Right | Replicates sign bit from the left | Preserves sign interpretation for negative numbers |
| `>>>` | Right | `0` from the left | Treats bit pattern as an unsigned value while shifting |

Example with an **illustrative 8-bit** pattern `0010 1100` (44 decimal):

```text
0010 1100  (44)
0101 1000  (shifted left by 1 -> 88)
0001 0110  (shifted right by 1 -> 22)
```

For non-negative numbers with no high bits lost, `>>` and `>>>` usually give the same result. The crucial difference appears with **negative numbers**.

**Note:** the 8-bit example above is only a visual illustration. In Java, `byte` and `short` operands are promoted to `int` before shifting; to accurately predict Java's result, always compute over the **32- or 64-bit** width of the actual expression.

## 2. Signed Integers and Reading the Highest Bit

Java uses **two's complement** representation for 32-bit `int` and 64-bit `long`:

- The highest bit of a signed bit pattern is the **sign bit**; `0` corresponds to non-negative numbers, `1` corresponds to negative numbers.
- For example, positive `int` 8 has the 32-bit pattern `00000000 00000000 00000000 00001000`.
- Negative `int` -8 has the 32-bit pattern `11111111 11111111 11111111 11111000`.

In this lesson, the term **"unsigned right shift"** describes **how `0` bits are inserted** by the `>>>` operator; it does not mean the operand becomes an unsigned data type. The result is still `int` or `long` depending on the expression's type.

### Visualizing -8 as a 32-bit `int`

```text
-8 (int):
11111111 11111111 11111111 11111000

-8 >> 2  (fills with sign bit 1):
11111111 11111111 11111111 11111110  = -2

-8 >>> 2 (fills with bit 0):
00111111 11111111 11111111 11111110  = 1073741822
```

Both shifts move the bits **2 positions to the right**, but `>>` preserves sign extension whereas `>>>` fills with 0. Because the leading bit of the `>>>` result above is 0, the result is interpreted as a positive `int`.

## 3. The `<<` Operator: Left Shift

Syntax:

```java
int result = value << distance;
```

Bits are pushed to the left, and vacated positions on the right are filled with `0`. For non-negative values and when the result still fits within the signed range, shifting left by `n` positions gives the same mathematical result as **multiplying by \(2^n\)**:

```java
int a = 3 << 1; // 6, equivalent to 3 * 2
int b = 3 << 2; // 12, equivalent to 3 * 4
int c = 5 << 3; // 40, equivalent to 5 * 8
```

However, the left shift operator **does not check for overflow**. Bits shifted past the left boundary are discarded; the sign of the result can change.

```java
int signBit = 1 << 31; // -2147483648
int wrapped = 1 << 32; // 1, because int shift distance is masked to low 5 bits
long wide = 1L << 32;  // 4294967296, left operand is long
```

In `1 << 31`, the 1 bit is moved into the sign position of `int`, making the result the negative value `Integer.MIN_VALUE`. With `1 << 32`, Java **does not shift by 32 positions**; the shift distance rule is explained separately in section 7.

**Do not treat `x << n` as a safe multiplication by \(2^n\)** in general. Bit shifting can drop high bits, overflow the range, or flip the sign; shifting also does not signal errors with exceptions. If business logic requires exact multiplication and overflow detection, consider `Math.multiplyExact` or `BigInteger`.

## 4. The `>>` Operator: Sign-Preserving Right Shift

Syntax:

```java
int result = value >> distance;
```

During a signed right shift, vacated positions on the left are filled with copies of the **highest bit**:

- Non-negative numbers: the sign bit is `0`, so `0` is inserted.
- Negative numbers: the sign bit is `1`, so `1` is inserted.

Example:

```java
int positive = 40 >> 2; // 10
int negative = -8 >> 2; // -2
int odd = -7 >> 1;      // -4
```

For signed integers, the result of `x >> n` corresponds to *floor* integer division of \(x / 2^n\), when interpreting the shift distance according to Java's rules. Therefore, be careful with odd negative numbers:

```java
System.out.println(-7 / 2);  // -3: integer division rounds toward 0
System.out.println(-7 >> 1); // -4: right shift rounds down
```

Java integer `/` **rounds toward 0**, whereas signed right shift on negative numbers effectively rounds toward negative infinity. The two are not always equivalent.

**When to use `>>`?** When you want to process bits within a signed integer type and preserve sign extension, or when a bit-level algorithm is explicitly defined in terms of arithmetic right shift.

## 5. The `>>>` Operator: Zero-Fill Right Shift

Syntax:

```java
int result = value >>> distance;
```

This operator always fills vacated positions on the left with `0` bits, regardless of the operand's sign. Example:

```java
int a = 40 >>> 2;   // 10
int b = -8 >>> 2;   // 1073741822
int c = -1 >>> 1;   // 2147483647
long d = -1L >>> 1; // 9223372036854775807L
```

For non-negative numbers, `>>` and `>>>` produce the same result for the same operand and shift distance. For negative numbers, `>>>` typically produces a **large positive** number because the initial `1` sign bit is replaced by `0`.

`>>>` is useful when reading bit fields, treating a bit pattern as an **unsigned bit pattern**, extracting bytes/bit groups from an integer, or implementing hashing, checksums, and binary encoding algorithms.

Do not confuse `>>>` with signed division. For example, `-8 / 4` equals -2; `-8 >>> 2` equals 1_073_741_822. If you want mathematical integer division in Java, use `/` or an appropriate API instead of substituting `>>>`.

## 6. Java 17+ Program Comparing All Three Operators

Create the file `ShiftOperatorsDemo.java`:

```java
public class ShiftOperatorsDemo {
    public static void main(String[] args) {
        int positive = 40;
        int negative = -8;

        System.out.println("40 << 2 = " + (positive << 2));
        System.out.println("40 >> 2 = " + (positive >> 2));
        System.out.println("40 >>> 2 = " + (positive >>> 2));

        System.out.println("-8 << 2 = " + (negative << 2));
        System.out.println("-8 >> 2 = " + (negative >> 2));
        System.out.println("-8 >>> 2 = " + (negative >>> 2));

        System.out.println("-1 >> 1 = " + (-1 >> 1));
        System.out.println("-1 >>> 1 = " + (-1 >>> 1));
        System.out.println("-7 / 2 = " + (-7 / 2));
        System.out.println("-7 >> 1 = " + (-7 >> 1));

        System.out.printf("hex(-8 >>> 2) = %08X%n", negative >>> 2);
    }
}
```

Compile and run with Java 17+:

```bash
javac ShiftOperatorsDemo.java
java ShiftOperatorsDemo
```

Exact output:

```text
40 << 2 = 160
40 >> 2 = 10
40 >>> 2 = 10
-8 << 2 = -32
-8 >> 2 = -2
-8 >>> 2 = 1073741822
-1 >> 1 = -1
-1 >>> 1 = 2147483647
-7 / 2 = -3
-7 >> 1 = -4
hex(-8 >>> 2) = 3FFFFFFE
```

Observe two points:

1. Left-shifting `-8 << 2` gives -32 in this example because the remaining bits happen to form -32, but you cannot conclude that every left shift is equivalent to safe arithmetic multiplication.
2. For `-8 >>> 2`, the hex result `3FFFFFFE` shows that the two leading `1` bits in the negative representation were replaced with two `0` bits.

## 7. Shift Distance and Left-Operand Type

Java does not throw an exception when the shift distance is negative or larger than the type width. The effective shift distance is masked according to the **left operand's type after promotion**, while the right operand's type does not determine the expression's bit width.

| Left-operand type | Effective shift distance | Example |
| --- | --- | --- |
| `int`, including promoted `byte`/`short`/`char` | `distance & 31` | `1 << 32 == 1` |
| `long` | `distance & 63` | `1L << 32 == 4294967296L` |

```java
int lowerWidth = 1 << 40;       // 256: 40 & 31 = 8
long higherWidth = 1L << 40;    // 1099511627776L
long assignedAfterShift = 1 << 40; // 256L: shift already happened in int
int negativeDistance = 1 << -1;   // Integer.MIN_VALUE: -1 & 31 = 31
```

A negative `byte` is also sign-extended to `int` before shifting: with `byte b = -8;`, `b >>> 2` gives `1073741822`, whereas `Byte.toUnsignedInt(b) >>> 2` gives `62`. When `index` comes from input to build a mask, explicitly check `0 <= index && index < 32` or `< 64` depending on the type before shifting; Java does not reject out-of-range indices.

The next lesson **Shift Distance Masking by `int` or `long`** explores negative distances, multiples of 32/64, `long` right-hand operands, and guarding indexed bit access.

## 8. Operator Precedence, Parentheses, and Conditional Expressions

The operators `<<`, `>>`, and `>>>` have the **same precedence** and left-to-right associativity. They have **lower precedence than addition/subtraction** but **higher precedence than relational comparison operators** like `<`, `>=`.

Example:

```java
int a = 1 << 2 + 1; // 8: interpreted as 1 << (2 + 1)
int b = (1 << 2) + 1; // 5
int c = 32 >> 1 >> 2; // 4: (32 >> 1) >> 2
boolean d = (1 << 3) > 7; // true
```

When writing conditions and bitmasks, add parentheses to reflect intent so readers do not need to memorize the precedence table. For example:

```java
int mask = 1 << 5;
boolean hasFlag = (flags & mask) != 0;
```

The snippet above is **illustrative code** requiring a previously declared `int flags` variable; `&` is bitwise AND and `!=` is inequality comparison. It tells whether bit 5 is currently set in the bit pattern of `flags`.

Shift operators only accept **integral-type** operands (after appropriate unboxing/promotion); you cannot directly shift `float`, `double`, or `String`. If using a wrapper like `Integer` whose value is `null`, unboxing for the shift will throw `NullPointerException`.

## 9. Practical Applications: Bitmasks and Extracting Bytes

### 11.1. Creating Bitmasks for Status Flags

To set bit `k` of an `int` variable:

```java
int flags = 0;
int readFlag = 1 << 2;   // 0b00000100
int writeFlag = 1 << 5;  // 0b00100000

flags |= readFlag;
flags |= writeFlag;
boolean canRead = (flags & readFlag) != 0;   // true
boolean canWrite = (flags & writeFlag) != 0; // true
```

These are statements that need to be placed inside a Java program with `main` or a method to run. `|` is bitwise OR, `|=` is OR assignment; `<<` simply places the 1 bit at the desired position. For `int`, meaningful bit positions are normally 0 through 31; for `long`, 0 through 63. Restrict `k` to this range to avoid shift-distance wrap-around creating the wrong mask.

### 11.2. Extracting Individual Bytes from a 32-bit Integer

Suppose `int word = 0x1234ABCD`. To retrieve the four bytes in high-to-low bit order, use `>>>` and the mask `0xFF`:

```java
int word = 0x1234ABCD;
int first  = (word >>> 24) & 0xFF; // 0x12 = 18
int second = (word >>> 16) & 0xFF; // 0x34 = 52
int third  = (word >>>  8) & 0xFF; // 0xAB = 171
int fourth = word & 0xFF;          // 0xCD = 205
```

The `& 0xFF` mask keeps only the **low 8 bits**. `>>>` is appropriate when extracting a bit field without dragging `1` sign bits into the upper positions of the result. In expressions with a tight enough mask, `>>` can sometimes yield the same low 8 bits; however, `>>>` clearly communicates logical shift intent.

**Endianness** (big-endian/little-endian) is the byte-ordering convention when storing or transmitting data. The shifts above only extract 8-bit groups by position within an **`int` value**; they do not determine byte order in a file or byte buffer. When writing externally, specify the byte order according to the protocol.

### 11.3. Runnable Program: Extracting Bytes

Create `ExtractBytesDemo.java`:

```java
public class ExtractBytesDemo {
    public static void main(String[] args) {
        int word = 0x1234ABCD;
        System.out.printf("%02X%n", (word >>> 24) & 0xFF);
        System.out.printf("%02X%n", (word >>> 16) & 0xFF);
        System.out.printf("%02X%n", (word >>> 8) & 0xFF);
        System.out.printf("%02X%n", word & 0xFF);
    }
}
```

Run:

```bash
javac ExtractBytesDemo.java
java ExtractBytesDemo
```

Output:

```text
12
34
AB
CD
```

`%02X` formats the number in uppercase hexadecimal and pads with zero so there are at least 2 digits when needed.

## 10. Where Shifts Can and Cannot Replace Multiplication/Division

Some useful approximations:

- For `x >= 0`, when no bits are lost and the result fits in the type: `x << n` has the same value as `x * 2^n`.
- For `x >= 0`: `x >> n` and `x >>> n` have the same value as integer division `x / 2^n` within valid shift distances.
- For `x < 0`: `x >> n` does **not always** equal `x / 2^n` because rounding directions differ.
- For `x < 0`: `x >>> n` interprets bits as unsigned and then shifts, so it is not equivalent to signed division.

Use `Math.multiplyExact` or compute in a wider type if exact arithmetic and overflow detection are required. Do not optimize business code by replacing `*` or `/` with shift operators without verifying behavior on negative numbers, boundary values, and large shift distances. The compiler/JIT can apply appropriate optimizations automatically when valid.

## 11. Common Mistakes

| Symptom | Cause | Fix / Takeaway |
|---|---|---|
| `-8 >>> 2` produces a huge positive number | `>>>` inserts `0` into high bits of 32-bit `int` | Use only when you want a logical bit-pattern shift |
| `1 << 32` still equals 1 | For `int`, only the low 5 bits of shift distance are used | Use `1L << 32` if you want \(2^{32}\) |
| `1L << 64` still equals 1 | For `long`, only the low 6 bits are used | Validate shift distance beforehand |
| `byte b = -8; b >>> 2` does not give 62 | `byte` is sign-promoted to `int` before shifting | Use `Byte.toUnsignedInt(b) >>> 2` |
| `byte b = 1; b = b << 1;` compile error | Shift produces an `int` result | Store in `int` or cast with range checking |
| `-7 >> 1` differs from `-7 / 2` | Signed right shift rounds down; integer division rounds toward 0 | Use `/` when you want Java division |
| `1 << 31` is negative | Places 1 into the sign bit of `int` | Understand two's complement and type range |
| `x << n` reports no overflow error | High bits are silently discarded | Use checked arithmetic if needed |
| `int x = 1; long y = x << 40;` gives an unexpected result | Shift runs in `int` before widening to `long` | Use `((long) x) << 40` |
| Hard-to-read bitmask conditions | Confusing precedence of `&`, `<<`, and comparisons | Add parentheses: `(flags & mask) != 0` |

## 12. Self-Check

**Question 1.** For `int x = 16`, what are `x << 1`, `x >> 2`, and `x >>> 2`?  
**Answer:** 32, 4, and 4, respectively.

**Question 2.** For `int x = -8`, what are `x >> 2` and `x >>> 2`?  
**Answer:** -2 and 1_073_741_822. The former fills with sign bit `1`, while the latter fills with `0`.

**Question 3.** Why does `1 << 32` return 1?  
**Answer:** the left operand has type `int`, so only the low 5 bits of the shift distance are used; 32 & 31 equals 0.

**Question 4.** How do you produce \(2^{32}\) using a shift?  
**Answer:** `1L << 32`, giving a `long` result of 4_294_967_296.

**Question 5.** Why is `byte b = -8; b >>> 2` not an 8-bit unsigned shift?  
**Answer:** `byte` is promoted to 32-bit `int` with sign extension before shifting. Use `Byte.toUnsignedInt(b) >>> 2` if you want the value 248 shifted to 62.

**Question 6.** For `int n = -7`, how do `n / 2` and `n >> 1` differ?  
**Answer:** -3 and -4 because the rounding rules of integer division and signed right shift differ for odd negative numbers.

**Question 7.** What is `(word >>> 16) & 0xFF` used for?  
**Answer:** it shifts the bit pattern of `word` right by 16 positions and keeps only the low 8 bits of the result (bits 16..23 of the original value).

**Question 8.** Does `long x = 1 << 40;` differ from `long y = 1L << 40;`?  
**Answer:** yes. `x` receives 256 because of an `int` shift with effective distance 8; `y` receives 1_099_511_627_776 because the shift operates on `long` with distance 40.

**Question 9.** Is left shift always a safe multiplication by \(2^n\)?  
**Answer:** no. High bits can be discarded or shifted into the sign bit; Java does not throw an exception on overflow in a shift operation.

**Remember:** `<<` shifts left and fills with `0`; `>>` shifts right and **preserves the sign bit**; `>>>` shifts right and **fills with `0`**. The result type depends on the **left operand after promotion**. `int` uses only the **low 5 bits** of the shift distance (0..31), and `long` uses only the **low 6 bits** (0..63). When manipulating negative `byte`/`short` values, especially with `>>>`, remember that Java performs the shift on a 32-bit `int` after promotion.