# Integer Narrowing and Discarded Bits in Java

> **Java core – numbers · Numeric Conversions**  
> Goal: determine exactly which bits remain after a narrowing integer conversion, how Java reinterprets signed and unsigned bits, and how to avoid data loss in conversions, assignments, and binary processing.

## 1. The problem: a large value entering a smaller type

In Java, integer types have fixed bit widths and value ranges:

| Type | Width | Range | Signed? |
| --- | ---: | --- | --- |
| `byte` | 8 bits | −128 to 127 | Yes |
| `short` | 16 bits | −32,768 to 32,767 | Yes |
| `char` | 16 bits | 0 to 65,535 | No |
| `int` | 32 bits | −2³¹ to 2³¹−1 | Yes |
| `long` | 64 bits | −2⁶³ to 2⁶³−1 | Yes |

*Integer narrowing* (*narrowing primitive conversion*) is converting an integer value to a target type that is not guaranteed to hold every value of the source type. For example:

```java
int source = 130;
byte result = (byte) source;
System.out.println(result); // -126
```

**Java does not pick the nearest value in the `byte` range.** When casting from a wider integer to a narrower integer, it discards the high bits and keeps only the **low n bits**, where n is the width of the target type; it then interprets this bit pattern according to the target type's rules. Because `130` has low 8 bits `1000_0010`, that pattern represents `−126` when interpreted as a two's-complement signed byte.

A narrowing integer conversion also does not automatically throw an exception when the original value cannot be preserved. A cast is a request to convert according to language rules, **not a promise that the value stays intact**.

## 2. Bit mechanism: cut on the left, keep on the right

Consider `int 130` (32 bits) to `byte` (8 bits):

```text
int (32 bits): 00000000 00000000 00000000 10000010
              \______ 24 high bits discarded ___/ \_ 8 bits _/
                                                   10000010

If read as UNSIGNED 8 bits: 128 + 2 = 130
If read as signed byte: 130 - 256 = -126
```

With `int 255`:

```text
int:    00000000 00000000 00000000 11111111
byte:                              11111111
                                              -> -1 (signed byte)
```

With `int 256`:

```text
int:    00000000 00000000 00000001 00000000
byte:                              00000000
                                              -> 0 (bit at position 8 was discarded)
```

To predict the result, you can use a two-step mathematical rule:

1. Find `U` as the **non-negative remainder** of the source number when divided by `2^n`. Then `U` lies in `0..2^n−1` and describes the low n bits.
2. If the target type is `char`, the result equals `U`. If the target type is n-bit signed, the result equals `U` when `U < 2^(n−1)`, or `U−2^n` when `U ≥ 2^(n−1)`.

For `(byte) 300`: `300 mod 256 = 44`, so the result is `44`. For `(byte) -130`: the **non-negative** remainder of −130 divided by 256 is 126, so the result is `126`.

**Note:** the `mod` notation above denotes the non-negative mathematical remainder. The `%` operator in Java can return a negative remainder if the dividend is negative; for instance, `-130 % 256 == -130`. To get the non-negative remainder with a positive modulus, you can use `Math.floorMod(-130, 256)`.

## 3. Pattern table: casting int to byte

| Source `int` | Low 8 bits | `(byte)` | Interpretation |
| ---: | --- | ---: | --- |
| 100 | `0110_0100` | 100 | Still fits in byte |
| 127 | `0111_1111` | 127 | Positive bound |
| 128 | `1000_0000` | −128 | Byte sign bit is set |
| 129 | `1000_0001` | −127 | Two's complement value |
| 130 | `1000_0010` | −126 | Two's complement value |
| 255 | `1111_1111` | −1 | All eight bits are 1 |
| 256 | `0000_0000` | 0 | Bit 8 was lost |
| 257 | `0000_0001` | 1 | Only bit 0 remains |
| −1 | `1111_1111` | −1 | Value still preserved |
| −128 | `1000_0000` | −128 | Negative bound |
| −129 | `0111_1111` | 127 | Wraps around the byte range |

For example, `(byte) 128` yields `−128`, while `(byte) 255` yields `−1`. There is no **clamping** logic to −128/127. Distinct source values separated by multiples of 256 share the same low 8-bit pattern and produce the same `byte` value.

## 4. Narrowing long to int

`long` is 64 bits and `int` is 32 bits. When casting `long → int`, Java discards the high 32 bits:

```java
long large = 0x1_0000_0001L; // 4294967297
int shortened = (int) large; // 1
```

```text
long: 00000001 00000001  (each group here is 32 bits in hex: 0x00000001_00000001)
               ^^^^^^^^
               low 32 bits = 0x00000001 -> int 1
```

To see a sign change:

```java
long source = 0x00000001_FFFFFFFFL;
int shortened = (int) source;
System.out.println(shortened); // -1
```

The low part `0xFFFFFFFF` of the `long` is kept as-is, which in signed `int` is −1.

When truncating IDs or quantity values from `long` to `int`, losing the high 32 bits can make many different values collapse to the same value. For example, `1L` and `0x1_0000_0001L` both cast to `int 1`. Only use narrowing to extract bits if **the specification genuinely requires bit extraction**; if values must be preserved, check the range before casting.

## 5. int to short: keeping 16 bits, signed interpretation

```java
System.out.println((short) 32767); // 32767
System.out.println((short) 32768); // -32768
System.out.println((short) 65535); // -1
System.out.println((short) 65536); // 0
```

```text
 32768 (0x00008000) -> keeps 0x8000 -> short -32768
 65535 (0x0000FFFF) -> keeps 0xFFFF -> short -1
 65536 (0x00010000) -> keeps 0x0000 -> short 0
```

Narrowing `long → short` has the same low 16 bits as its target. Going through `int` first and then converting to `short` (with no intermediate operations altering the value) also preserves the same low 16 bits.

## 6. char: same 16 bits as short, but unsigned

`char` is an unsigned UTF-16 code unit, with numeric values from 0 to 65,535. Narrowing to `char` still keeps the low 16 bits, but **does not use the highest bit as a sign bit**:

```java
char a = (char) 65;       // 'A'
char b = (char) 65535;    // numeric value 65535
char c = (char) 65536;    // numeric value 0
char d = (char) -1;       // numeric value 65535
System.out.println((int) d); // 65535
```

When printing a `char` variable directly, Java may print the **character**, not the numeric code. To inspect the numeric code, cast `char` up to `int` as shown above.

Comparing the two 16-bit types:

```java
char unit = '\uFFFF';
short signed = (short) unit;   // -1
char restored = (char) signed; // 65535
```

The 16 bits `1111_1111_1111_1111` themselves do not change. However, `short` reads them as −1 while `char` reads them as 65,535. Because their ranges differ, converting between these two types requires a cast despite having the same bit count. You should not treat `char` as a generic substitute unsigned numeric type for data: a UTF-16 code unit is not necessarily a standalone Unicode character or a printable character.

## 7. Chained casts: still keep low bits when no operations intervene

```java
long number = 0x1234_5678_9ABC_DEF0L;

int low32 = (int) number;       // 0x9ABCDEF0
short low16 = (short) number;   // 0xDEF0
byte low8 = (byte) number;      // 0xF0
```

```text
long:   1234 5678 9ABC DEF0
int:              9ABC DEF0
short:                 DEF0
byte:                    F0
```

You can verify that `(byte) number`, `(byte)(int) number`, and `(byte)(short) number` all become `−16`, because the low 8 bits are always `0xF0`. This equivalence holds only when the intermediate steps are purely integer conversions. Inserting arithmetic operations, casting through `float`/`double`, or bit shifts can produce different patterns.

## 8. Why some assignments do not need a cast: constant expressions

Narrowing from an `int` variable to `byte` normally requires a cast:

```java
int value = 100;
// byte invalid = value; // error: int variable cannot be implicitly narrowed
byte explicit = (byte) value;
```

However, Java has an exception—**assignment conversion for constant expressions** of type `byte`, `short`, `char`, or `int`—if the value falls within the range of the target type:

```java
byte a = 100;          // ok: int literal 100 fits in byte
short b = 30000;       // ok: int constant fits in short
char c = 65;           // ok: int constant is within char range
byte total = 40 + 2;   // ok: int constant expression equals 42

final int FIXED = 120;
byte fromFixed = FIXED; // ok: final int constant variable

int ordinary = 120;
// byte wrong = ordinary; // not allowed

// byte tooLarge = 128;  // not allowed: out of range
byte wrapped = (byte) 128; // ok: -128
```

Distinguish clearly between the **exception for in-range constant assignment** and an explicit cast: the compiler knows the constant value and allows the assignment if safe; an out-of-range explicit cast still keeps the low bits and can lose the value. This constant-assignment rule also **does not mean** any method call taking a `byte` can accept an `int` literal without a cast.

## 9. Numeric promotion: arithmetic executes before narrowing

In addition, subtraction, multiplication, and division between integer primitives, `byte`, `short`, and `char` operands are usually promoted to `int` first (*binary numeric promotion*).

```java
byte x = 100;
byte y = 30;
int sum = x + y;           // 130, type int
byte result = (byte) (x + y); // -126
// byte invalid = x + y;  // error: sum has type int
```

If a calculation runs in `int` and **overflows before the cast**, casting afterward cannot restore the lost information:

```java
int a = 1_500_000_000;
long bad = a * 2;           // -1294967296L, int overflowed first
long good = (long) a * 2;  // 3000000000L, long before multiplication
```

When you need overflow checking in `int`/`long`, use `Math.addExact`, `Math.multiplyExact`, and related exact methods; when you need an integer range larger than `long`, convert operands to `BigInteger` **before the operation**.

Do not confuse the rules above with casting from floating-point to integer. `(int) 3.9` follows the rule of discarding the fractional part, while `(byte) 130` follows the rule of keeping the low bits. Floating-point `NaN`, infinities, and out-of-range values have their own rules, which are outside the focus of this lesson.

## 10. Compound assignment and ++/--: implicit narrowing applies

Compound assignment (`+=`, etc.) includes an implicit conversion back to the left-hand type:

```java
byte b = 127;
b += 1;
System.out.println(b); // -128
```

Regular assignment behaves differently:

```java
byte b = 127;
// b = b + 1; // error: b + 1 is int
b = (byte) (b + 1); // -128
```

Conceptually, `E1 op= E2` is close to `E1 = (T)(E1 op E2)`, with one essential difference: **E1 is evaluated only once**. Therefore, do not substitute one for the other casually if the left-hand side involves array access, index increments, or method calls.

The `++`/`--` operators on `byte`, `short`, and `char` can also wrap around:

```java
byte b = 127;
b++;
System.out.println(b); // -128

char unit = '\uFFFF';
unit++;
System.out.println((int) unit); // 0
```

If business logic does not permit wraparound, use a sufficiently wide type and check the range before assignment.

## 11. Masking and interpreting unsigned bytes

In Java, `byte` is signed. However, binary/protocol formats often use an **unsigned** octet from 0..255:

```java
byte raw = (byte) 0xFF;  // signed byte -1
int signed = raw;        // -1: sign extension when widening to int
int unsigned = raw & 0xFF; // 255: keeps low 8 bits
int api = Byte.toUnsignedInt(raw); // 255
```

The difference:

- `byte → int` is **widening** that preserves the signed value: the sign bit `1` is extended into the high 24 bits.
- `raw & 0xFF` is a mask operation after the operand has been promoted to `int`: it clears the high bits to keep a value in 0..255.

When combining two big-endian octets:

```java
byte high = (byte) 0xAB;
byte low = (byte) 0xCD;
int unsigned16 = ((high & 0xFF) << 8) | (low & 0xFF);
System.out.println(unsigned16); // 43981 (0xABCD)
```

Masking each byte before shifting/OR-ing prevents sign extension from corrupting bits. Practical rule: identify the **field width, signedness, and byte order** from the protocol specification; cast down to `byte` only when you truly want the low bits, and use range checks when you need to preserve the **arithmetic value**.

## 12. Detecting data loss before casting

### 12.1. Range check before narrowing

```java
public static byte checkedByte(int value) {
    if (value < Byte.MIN_VALUE || value > Byte.MAX_VALUE) {
        throw new ArithmeticException("Outside byte range");
    }
    return (byte) value;
}
```

This is an **illustrative method**; place it inside a class before using it. For `short`, use `Short.MIN_VALUE`/`Short.MAX_VALUE`. For `char`, use `value >= Character.MIN_VALUE && value <= Character.MAX_VALUE`.

### 12.2. Math.toIntExact and BigInteger exact

```java
long large = 0x1_0000_0001L;
int truncated = (int) large; // 1
// Math.toIntExact(large) will throw ArithmeticException
```

`Math.toIntExact(long)` is a built-in API to require converting to `int` **without losing value**. `BigInteger` provides `byteValueExact()`, `shortValueExact()`, `intValueExact()`, and `longValueExact()`. By contrast, `BigInteger.intValue()` and `longValue()` can drop high bits without reporting an error.

### 12.3. Round-trip cast check

```java
int original = 130;
byte narrowed = (byte) original;
boolean preserved = ((int) narrowed == original); // false
```

This is a way to self-verify loss, though when validating real input, **checking the range before casting** is more readable and avoids confusion when converting through unsigned `char`.

## 13. Standalone runnable Java 17+ program

Create the file **`IntegerNarrowingDemo.java`**:

```java
public class IntegerNarrowingDemo {
    private static byte checkedByte(int value) {
        if (value < Byte.MIN_VALUE || value > Byte.MAX_VALUE) {
            throw new ArithmeticException("byte range exceeded");
        }
        return (byte) value;
    }

    private static String bits8(int value) {
        String binary = Integer.toBinaryString(value & 0xFF);
        return String.format("%8s", binary).replace(' ', '0');
    }

    public static void main(String[] args) {
        int source = 130;
        byte narrowed = (byte) source;

        System.out.println("130 -> byte = " + narrowed);
        System.out.println("low 8 bits = " + bits8(source));
        System.out.println("255 -> byte = " + (byte) 255);
        System.out.println("256 -> byte = " + (byte) 256);
        System.out.println("-129 -> byte = " + (byte) -129);

        long wide = 0x1_0000_0001L;
        System.out.println("long -> int = " + (int) wide);
        System.out.println("32768 -> short = " + (short) 32768);
        System.out.println("-1 -> char code = " + (int) (char) -1);

        byte octet = (byte) 0xFF;
        System.out.println("signed byte = " + octet);
        System.out.println("unsigned octet = " + Byte.toUnsignedInt(octet));

        byte counter = 127;
        counter += 1;
        System.out.println("byte += 1 = " + counter);

        try {
            checkedByte(130);
        } catch (ArithmeticException e) {
            System.out.println("checked byte: rejected");
        }
        try {
            Math.toIntExact(wide);
        } catch (ArithmeticException e) {
            System.out.println("toIntExact: rejected");
        }
    }
}
```

Run in the directory containing the file:

```bash
javac IntegerNarrowingDemo.java
java IntegerNarrowingDemo
```

**Exact stdout:**

```text
130 -> byte = -126
low 8 bits = 10000010
255 -> byte = -1
256 -> byte = 0
-129 -> byte = 127
long -> int = 1
32768 -> short = -32768
-1 -> char code = 65535
signed byte = -1
unsigned octet = 255
byte += 1 = -128
checked byte: rejected
toIntExact: rejected
```

Reading the output:

1. `130` becomes `-126` because `10000010` is signed byte −126.
2. `255` becomes `−1`, `256` becomes `0`, and `−129` becomes `127` due to the same modulo-256 rule at the bit level.
3. `long 0x1_0000_0001L` loses its high 32 bits and becomes `int 1`; casting to `short`/`char` likewise keeps the low bits of the target type.
4. The same octet `0xFF` is read as signed byte −1 or unsigned 255.
5. `+=` narrows implicitly and wraps around; the checked helpers reject non-value-preserving conversions.

## 14. Common mistakes

| Misconception | Correct rule |
| --- | --- |
| `(byte) 130` clamps at 127 | Keeps low 8 bits, returns −126 |
| Narrowing integer cast reports overflow automatically | Cast does not report it; you must check bounds |
| Integer narrowing is arithmetic rounding | It discards high bits and interprets target bits |
| `short` and `char` are both 16 bits so they have the same values | `short` is signed, `char` is unsigned |
| `(char) -1` still equals −1 | Its value is 65535 |
| Negative `byte` widened to `int` becomes 0..255 | Widening preserves sign; mask if unsigned is needed |
| `byte + byte` is still `byte` | Binary arithmetic operators promote to `int` |
| `byte b = 100;` proves any int→byte assignment works | That is an exception for in-range constants |
| `byte += 1` checks overflow | Compound assignment narrows implicitly |
| Casting after multiplication recovers earlier overflow | Lost information does not come back |
| Mask and cast always have equal values | Mask is for unsigned bits; cast preserves the signed target type |
| Casting to `char` produces a valid Unicode scalar value | `char` is only a UTF-16 code unit |

## 15. Practice exercises with solutions

**Exercise 1.** What does `(byte) 300` equal?  
**Solution:** `300 mod 256 = 44`, bit pattern `00101100`, result **44**.

**Exercise 2.** What numeric values do `(short) 65535` and `(char) 65535` produce?  
**Solution:** the same pattern `FFFF`, but **−1** and **65535** respectively. Print with `(int)(short)65535` and `(int)(char)65535`.

**Exercise 3.** What does `(int) 0x0000_0002_0000_0005L` equal?  
**Solution:** **5**; only the low 32 bits `00000005` remain.

**Exercise 4.** Which statements compile: `byte a = 127;`, `byte b = 128;`, `byte c = (byte)128;`?  
**Solution:** `a` compiles (=127), `b` fails to compile due to out-of-range constant, `c` compiles (=−128).

**Exercise 5.** Given `byte b = (byte)0xFE;`, what are `b`, `(int)b`, and `b & 0xFF`?  
**Solution:** **−2**, **−2**, **254**. Widening to `int` preserves sign; masking reads the 8 bits as unsigned.

**Exercise 6.** How do you reject an `int` outside the `short` range?  
**Solution:** check `x >= Short.MIN_VALUE && x <= Short.MAX_VALUE` before `(short)x`; if false, return or throw an appropriate error.

**Exercise 7.** Why does `b += 1` work for `byte b` while `b = b + 1` does not?  
**Solution:** `+=` includes an implicit narrowing to the left-hand type; `b + 1` is `int` and ordinary assignment does not implicitly narrow an `int` variable.

## 16. Checklist before narrowing

1. Identify the **target bit width** and which bits will be discarded.
2. Distinguish **signed types** from unsigned `char`; the same bits can carry different values.
3. Clarify whether you need to **preserve the numeric value** or just extract **low bits** for a protocol.
4. Check **which operations happen before the cast**, and whether promotion or overflow occurs.
5. If information must not be lost, use **range checks**, `Math.toIntExact`, or the appropriate `BigInteger.*ValueExact` methods.
6. Check `+=`/`++` for implicit narrowing; watch the ±128, ±32,768, ±2³¹ boundaries.
7. For binary bytes, determine whether the protocol is **signed/unsigned** and mask properly before shifting/OR-ing.
8. Test both sides of boundaries yourself: in-range values, exact boundary values, and just outside the boundary.

**Point to remember:** Narrowing between integer types in Java **keeps the low n bits of the target type and discards the high bits**. The final result depends on how the target type interprets those n bits, signed or unsigned. An explicit cast does not guarantee zero data loss; bounds checking is what guarantees preserving the arithmetic value.
